import io
import json
import logging
import uuid
from datetime import date as date_type
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.runtime_paths import CONFIG_DIR, FRONTEND_DIST, ensure_runtime_files, get_output_dir, set_output_dir, build_output_path

from backend.stages.category_mapping import normalize_loose, EXCLUDED
from backend.stages.learned_overrides import load_learned_overrides, add_learned_overrides
from backend.stages.daily_history import record_day, load_history
from backend.stages.mtd import compute_mtd_columns
from backend.monthly_average import compute_month_column, finalize_month
from backend.format_validator import validate_upload, reset_baseline
from backend.verification import run_verification, save_verification, load_verification_history
from backend.stages.detection import detect_report_type, refine_billing_type_evidence
from backend.stages.date_detection import detect_report_date, detect_dates_from_filenames
from backend.stages.loading import build_dataframes, make_candidate_id
from backend.stages.pipeline import run_pipeline, StageProcessingError
from backend.stages.final_output import write_final_output
from backend.stages.reports import REPORT_TYPES

ensure_runtime_files()

VALID_BUCKETS = {"General", "TPA", "ECHS", "P CARD FUND", "CPR"}

app = FastAPI(title="Daily HIS Report Automation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory state for the most recently processed run -- lets the Category
# Review panel re-trigger recalculation without re-uploading files. Single
# office-PC daily tool, so this doesn't need to survive a restart or serve
# concurrent runs; it's keyed by file_id in case that changes later.
RUN_STATE: dict = {}


def _summarize(values: dict) -> dict:
    return {
        "Bed Occupancy %": values.get("Occupancy %"),
        "OP Encounters": values.get("OP Encounters"),
        "Total Billing": values.get("Total Billing"),
        "AEPL Billing": values.get("AEPL Billing"),
    }


def _warnings_from_category_review(category_review: dict) -> list:
    warnings = []
    unmatched = category_review.get("unmatched", [])
    possible = category_review.get("possible_matches", [])

    if unmatched:
        total_rows = sum(entry["frequency"] for entry in unmatched)
        sample = ", ".join((str(entry["raw_value"]) if entry["raw_value"] is not None else "(blank)") for entry in unmatched[:3])
        more = f" (+{len(unmatched) - 3} more)" if len(unmatched) > 3 else ""
        warnings.append(
            f"{len(unmatched)} unmatched category value(s) across {total_rows} row(s) "
            f"(e.g. {sample}{more}) — excluded from category-based totals. See Category Review."
        )

    if possible:
        warnings.append(
            f"{len(possible)} category value(s) have a possible match awaiting your confirmation "
            "— see Category Review panel."
        )

    return warnings


def _build_result_response(file_id: str, values: dict, category_review: dict, download_url: str, verification: dict = None) -> dict:
    warnings = _warnings_from_category_review(category_review)
    return {
        "status": "warning" if warnings else "success",
        "file_id": file_id,
        "summary": _summarize(values),
        "values": values,
        "warnings": warnings,
        "category_review": category_review,
        "verification": verification,
        "download_url": download_url,
    }


def _run_verification_safely(values: dict, dataframes: dict, report_date) -> dict:
    """Verification is diagnostics: if it crashes wholesale, log and carry on
    -- it must never turn a successful pipeline run into an error."""
    try:
        report = run_verification(values, dataframes)
        save_verification(report_date, report)
        return report
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("verification stage failed to run: %s", exc)
        return None


def _record_history(report_date, values: dict) -> None:
    # Persist today's figures for this month -- needed for MTD/Daily Average
    # regardless of whether the user ever downloads a spreadsheet.
    record_day(report_date, values, metric_keys=list(values.keys()))


def _build_output_file(values: dict, report_date) -> str:
    """Renders Final output.xlsx on demand (only called from /download), so a
    workbook is only ever written to disk when the user actually exports."""
    history = load_history()
    # None when this month has no day-1 snapshot -> columns written as "-".
    mtd_columns = compute_mtd_columns(report_date, values, history)

    # Roll every completed month in history into a static 2-col pair
    # ("-" pair if that month never recorded a day 1).
    finalized_months = {}
    for month_key_str in history:
        year, month = map(int, month_key_str.split("-"))
        if (year, month) < (report_date.year, report_date.month):
            finalized_months[(year, month)] = finalize_month(year, month)

    output_path = build_output_path(report_date)
    write_final_output(
        template_path=CONFIG_DIR / "final_output_template.xlsx",
        output_path=output_path,
        values=values,
        report_date=report_date,
        mtd_columns=mtd_columns,
        finalized_months=finalized_months,
    )
    return str(output_path)


@app.post("/detect")
async def detect(files: list[UploadFile] = File(...)):
    candidates = []
    sheets_for_date_detection = []
    for upload in files:
        content = await upload.read()
        try:
            excel_file = pd.ExcelFile(io.BytesIO(content))
        except Exception as exc:  # noqa: BLE001 - surfaced as a plain-language per-file problem
            return {
                "candidates": [],
                "matches": [],
                "missing": REPORT_TYPES,
                "detected_date": None,
                "file_error": {"source_file": upload.filename, "reason": f"Could not read this as an Excel file: {exc}"},
            }

        for sheet_name in excel_file.sheet_names:
            preview = excel_file.parse(sheet_name=sheet_name, header=None, nrows=20)
            preview_rows = preview.values.tolist()
            detection = detect_report_type(sheet_name, preview_rows)
            report_types = detection["report_types"]

            # A generic combined bill-list sheet matches both billing types
            # from its header alone (see detection.py::_match_by_columns).
            # Confirm which one(s) it actually contains before offering it
            # for both -- a 20-row preview can miss IP rows a documented
            # convention stacks far below the OP rows in the same sheet, so
            # re-scan the full sheet's Bill Type column when this ambiguity
            # comes up (only ever for sheets already billing-shaped).
            if {"Billing INR OP", "Billing INR IP"} <= set(report_types):
                full_rows = excel_file.parse(sheet_name=sheet_name, header=None).values.tolist()
                evidence = refine_billing_type_evidence(full_rows, detection["header_row"], full_rows[detection["header_row"]])
                refined = [rt for rt, seen in (("Billing INR OP", evidence["op"]), ("Billing INR IP", evidence["ip"])) if seen]
                if refined:
                    report_types = refined

            candidates.append(
                {
                    "id": make_candidate_id(upload.filename, sheet_name),
                    "source_file": upload.filename,
                    "sheet_name": sheet_name,
                    "report_type": report_types[0] if report_types else None,
                    "report_types": report_types,
                    "confidence": detection["confidence"],
                    "curated": detection["curated"],
                }
            )
            if detection["report_type"]:
                sheets_for_date_detection.append((detection["header_row"], preview_rows))

    # Multiple sheets in the uploaded workbook(s) can match the same report
    # type at equal confidence (e.g. a raw HIS export alongside a staff-
    # curated copy with Domestic/International + Cash/Credit already tagged).
    # Picking whichever came first silently prefers the raw sheet, which can
    # be missing/misaligned rows the curated sheet already corrected -- so
    # rank by confidence first, then prefer the curated sheet as a tie-break,
    # not upload/sheet order. A single candidate sheet can also legitimately
    # satisfy more than one report type at once (a combined OP+IP bill list,
    # see detection.py::_match_by_columns) -- iterate every type it matches,
    # not just its primary one, so it can auto-fill both slots instead of
    # leaving the second stuck on "needs manual assignment".
    CONFIDENCE_RANK = {"high": 2, "medium": 1, "none": 0}
    best_by_type = {}
    type_order = []
    for candidate in candidates:
        for report_type in candidate["report_types"]:
            if report_type not in best_by_type:
                type_order.append(report_type)
            rank = (CONFIDENCE_RANK[candidate["confidence"]], candidate["curated"])
            if report_type not in best_by_type or rank > best_by_type[report_type][0]:
                best_by_type[report_type] = (rank, candidate)

    matches = [
        {
            "report_type": report_type,
            "candidate_id": best_by_type[report_type][1]["id"],
            "confidence": best_by_type[report_type][1]["confidence"],
        }
        for report_type in type_order
    ]
    matched_types = set(type_order)

    missing = [rt for rt in REPORT_TYPES if rt not in matched_types]

    filename_result = detect_dates_from_filenames([upload.filename for upload in files])
    detected_date = filename_result["date"]
    if detected_date is None and not filename_result["conflict"]:
        detected_date = detect_report_date(sheets_for_date_detection)

    return {
        "candidates": [
            {"id": c["id"], "source_file": c["source_file"], "sheet_name": c["sheet_name"]} for c in candidates
        ],
        "matches": matches,
        "missing": missing,
        "detected_date": detected_date,
        "date_conflict": filename_result["conflict"],
    }


@app.post("/process")
async def process(
    files: list[UploadFile] = File(...),
    mapping: str = Form(...),
    date: str = Form(...),
):
    try:
        report_date = date_type.fromisoformat(date)
    except ValueError:
        return {"status": "error", "failed_file": None, "reason": f"Invalid date: {date!r}. Expected YYYY-MM-DD."}

    try:
        mapping_dict = json.loads(mapping)
    except json.JSONDecodeError:
        return {"status": "error", "failed_file": None, "reason": "Malformed report mapping."}

    missing = [rt for rt in REPORT_TYPES if rt not in mapping_dict]
    if missing:
        return {
            "status": "error",
            "failed_file": None,
            "reason": f"No report assigned for: {', '.join(missing)}.",
        }

    file_bytes = {}
    for upload in files:
        if not upload.filename.lower().endswith((".xlsx", ".xls")):
            return {
                "status": "error",
                "failed_file": upload.filename,
                "reason": f"'{upload.filename}' is not an Excel file (.xlsx/.xls).",
            }
        file_bytes[upload.filename] = await upload.read()

    # Stage 0: schema validation against baselines. Hard fail blocks the run
    # (all 9 reports are mandatory, so a blocked category blocks processing).
    schema_error, _schema_warnings = validate_upload(mapping_dict, file_bytes)
    if schema_error:
        return {
            "status": "error",
            "success": False,
            "error": schema_error,
            "failed_file": schema_error["category"],
            "reason": (
                f"Schema mismatch in {schema_error['category']}: expected column(s) missing: "
                f"{', '.join(schema_error['missingColumns'])}. If the HIS export format has "
                "genuinely changed, reset this report's baseline and re-upload."
            ),
        }

    try:
        dataframes = build_dataframes(mapping_dict, file_bytes)
    except ValueError as exc:
        return {"status": "error", "failed_file": None, "reason": str(exc)}

    # Seed with previously-accepted corrections so a value fixed on an earlier
    # day doesn't need re-confirming every run.
    overrides = dict(load_learned_overrides())
    try:
        values, category_review = run_pipeline(dataframes, overrides=overrides)
    except StageProcessingError as exc:
        return {"status": "error", "failed_file": exc.label, "reason": exc.reason}
    except Exception as exc:  # noqa: BLE001 - last-resort guard, still reported in plain language
        return {"status": "error", "failed_file": None, "reason": str(exc)}

    file_id = uuid.uuid4().hex
    _record_history(report_date, values)
    verification = _run_verification_safely(values, dataframes, report_date)

    RUN_STATE[file_id] = {
        "dataframes": dataframes,
        "report_date": report_date,
        "overrides": overrides,
        "values": values,
        "category_review": category_review,
    }

    return _build_result_response(file_id, values, category_review, f"/download/{file_id}", verification)


@app.get("/api/monthly-average")
def monthly_average(date: str, metric: str = "Total Billing"):
    # ponytail: spec's response shape is per-metric scalars; defaulting the
    # metric to Total Billing (row 34) -- pass ?metric= for any other row key.
    try:
        report_date = date_type.fromisoformat(date)
    except ValueError:
        return {"success": False, "error": "date must be YYYY-MM-DD"}

    column = compute_month_column(report_date, metric)
    if column is None:
        return {
            "success": True,
            "data": {"monthAvailable": False, "asOf": None, "dailyAverage": None, "mtdProjected": None},
        }
    return {"success": True, "data": {"monthAvailable": True, **column}}


@app.get("/api/verification-report")
def verification_report(date: str):
    try:
        report_date = date_type.fromisoformat(date)
    except ValueError:
        return {"success": False, "error": "date must be YYYY-MM-DD"}
    report = load_verification_history().get(report_date.isoformat())
    if report is None:
        return {"success": False, "error": f"No verification report recorded for {date}."}
    return {"success": True, "data": report}


class BaselineResetRequest(BaseModel):
    category: str


@app.post("/api/schema-baseline/reset")
def schema_baseline_reset(payload: BaselineResetRequest):
    if payload.category not in REPORT_TYPES:
        return {"success": False, "error": f"Unknown report category: {payload.category!r}."}
    reset_baseline(payload.category)
    return {"success": True, "data": {"category": payload.category, "message": "Baseline reset. The next upload's headers become the new baseline."}}


class OutputDirRequest(BaseModel):
    output_dir: str


@app.get("/api/settings")
def get_settings():
    return {"output_dir": str(get_output_dir())}


@app.post("/api/settings")
def update_settings(payload: OutputDirRequest):
    try:
        path = set_output_dir(payload.output_dir)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Can't use that folder: {exc}")
    return {"output_dir": str(path)}


@app.get("/download/{file_id}")
def download(file_id: str):
    state = RUN_STATE.get(file_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No processed run found for this id")
    output_path = _build_output_file(state["values"], state["report_date"])
    return FileResponse(
        output_path,
        filename=Path(output_path).name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/category-review")
def get_category_review(file_id: str):
    if file_id not in RUN_STATE:
        raise HTTPException(status_code=404, detail="No processed run found for this id.")
    return RUN_STATE[file_id]["category_review"]


class CategoryResolution(BaseModel):
    raw_value: str
    chosen_bucket: Optional[str] = None  # one of VALID_BUCKETS, or None to explicitly exclude


class CategoryResolveRequest(BaseModel):
    file_id: str
    resolutions: list[CategoryResolution]


@app.post("/category-review/resolve")
def resolve_category_review(payload: CategoryResolveRequest):
    if payload.file_id not in RUN_STATE:
        raise HTTPException(status_code=404, detail="No processed run found for this id.")

    if not payload.resolutions:
        return {"status": "error", "failed_file": None, "reason": "No resolutions provided."}

    # Never trust the frontend dropdown alone -- re-validate every chosen
    # bucket against the fixed 5-value enum server-side.
    invalid_buckets = sorted(
        {r.chosen_bucket for r in payload.resolutions if r.chosen_bucket is not None and r.chosen_bucket not in VALID_BUCKETS}
    )
    if invalid_buckets:
        return {
            "status": "error",
            "failed_file": None,
            "reason": f"Unknown bucket(s) {invalid_buckets}. Must be one of {sorted(VALID_BUCKETS)} or null to exclude.",
        }

    state = RUN_STATE[payload.file_id]
    new_entries = {
        normalize_loose(r.raw_value): (r.chosen_bucket if r.chosen_bucket is not None else EXCLUDED)
        for r in payload.resolutions
    }
    state["overrides"].update(new_entries)
    # Persisted separately from config/category_map.json (the master table) --
    # this only remembers reviewed exceptions (bucket or excluded) so they
    # don't need re-confirming on future days; it never rewrites the actual
    # Category Codes mapping.
    add_learned_overrides(new_entries)

    try:
        values, category_review = run_pipeline(
            state["dataframes"],
            overrides=state["overrides"],
        )
    except StageProcessingError as exc:
        return {"status": "error", "failed_file": exc.label, "reason": exc.reason}

    state["values"] = values
    state["category_review"] = category_review
    _record_history(state["report_date"], values)
    verification = _run_verification_safely(values, state["dataframes"], state["report_date"])

    return _build_result_response(payload.file_id, values, category_review, f"/download/{payload.file_id}", verification)


# Serve the built React app (frozen exe / production). Mounted last so every
# API route above wins; html=True serves index.html at "/". Absent in dev --
# there the Vite server on :5173 serves the UI and proxies the API here.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
