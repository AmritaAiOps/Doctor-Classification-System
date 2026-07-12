import io
import json
import uuid
from datetime import date as date_type
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.stages.category_mapping import normalize_loose, EXCLUDED
from backend.stages.learned_overrides import load_learned_overrides, add_learned_overrides
from backend.stages.daily_history import record_day
from backend.stages.mtd import compute_mtd_columns
from backend.stages.detection import detect_report_type
from backend.stages.date_detection import detect_report_date
from backend.stages.loading import build_dataframes, make_candidate_id
from backend.stages.pipeline import run_pipeline, StageProcessingError
from backend.stages.final_output import write_final_output
from backend.stages.reports import REPORT_TYPES

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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
_last_file_id: str = None


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


def _build_result_response(values: dict, category_review: dict, download_url: str) -> dict:
    warnings = _warnings_from_category_review(category_review)
    return {
        "status": "warning" if warnings else "success",
        "summary": _summarize(values),
        "values": values,
        "warnings": warnings,
        "category_review": category_review,
        "download_url": download_url,
    }


def _write_output(file_id: str, values: dict, report_date) -> str:
    # Persist today's figures for this month before computing MTD/Daily
    # Average, so today's own entry is included in the running sum.
    history = record_day(report_date, values, metric_keys=list(values.keys()))
    mtd_columns = compute_mtd_columns(report_date, values, history)

    work_dir = OUTPUT_DIR / file_id
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path = work_dir / "Final output.xlsx"
    write_final_output(
        template_path=BASE_DIR / "config" / "final_output_template.xlsx",
        output_path=output_path,
        values=values,
        date_column="F",
        report_date=report_date,
        mtd_columns=mtd_columns,
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
            candidates.append(
                {
                    "id": make_candidate_id(upload.filename, sheet_name),
                    "source_file": upload.filename,
                    "sheet_name": sheet_name,
                    "report_type": detection["report_type"],
                    "confidence": detection["confidence"],
                }
            )
            if detection["report_type"]:
                sheets_for_date_detection.append((detection["header_row"], preview_rows))

    matches = []
    matched_types = set()
    for candidate in candidates:
        report_type = candidate["report_type"]
        if report_type and report_type not in matched_types:
            matches.append(
                {
                    "report_type": report_type,
                    "candidate_id": candidate["id"],
                    "confidence": candidate["confidence"],
                }
            )
            matched_types.add(report_type)

    missing = [rt for rt in REPORT_TYPES if rt not in matched_types]
    detected_date = detect_report_date(sheets_for_date_detection)

    return {
        "candidates": [
            {"id": c["id"], "source_file": c["source_file"], "sheet_name": c["sheet_name"]} for c in candidates
        ],
        "matches": matches,
        "missing": missing,
        "detected_date": detected_date,
    }


@app.post("/process")
async def process(
    files: list[UploadFile] = File(...),
    mapping: str = Form(...),
    date: str = Form(...),
):
    global _last_file_id

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
    _write_output(file_id, values, report_date)

    RUN_STATE[file_id] = {
        "dataframes": dataframes,
        "report_date": report_date,
        "overrides": overrides,
        "values": values,
        "category_review": category_review,
    }
    _last_file_id = file_id

    return _build_result_response(values, category_review, f"/download/{file_id}")


@app.get("/download/{file_id}")
def download(file_id: str):
    output_path = OUTPUT_DIR / file_id / "Final output.xlsx"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="No processed output found for this id")
    return FileResponse(
        output_path,
        filename="Final output.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/category-review")
def get_category_review():
    if _last_file_id is None or _last_file_id not in RUN_STATE:
        raise HTTPException(status_code=404, detail="No processed run yet.")
    return RUN_STATE[_last_file_id]["category_review"]


class CategoryResolution(BaseModel):
    raw_value: str
    chosen_bucket: Optional[str] = None  # one of VALID_BUCKETS, or None to explicitly exclude


class CategoryResolveRequest(BaseModel):
    resolutions: list[CategoryResolution]


@app.post("/category-review/resolve")
def resolve_category_review(payload: CategoryResolveRequest):
    if _last_file_id is None or _last_file_id not in RUN_STATE:
        raise HTTPException(status_code=404, detail="No processed run to apply an override to.")

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

    state = RUN_STATE[_last_file_id]
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
    _write_output(_last_file_id, values, state["report_date"])

    return _build_result_response(values, category_review, f"/download/{_last_file_id}")
