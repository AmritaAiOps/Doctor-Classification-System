import io
import json
import uuid
from datetime import date as date_type
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.stages.detection import detect_report_type
from backend.stages.date_detection import detect_report_date
from backend.stages.loading import build_dataframes, make_candidate_id
from backend.stages.pipeline import run_pipeline, StageProcessingError
from backend.stages.final_output import write_final_output
from backend.stages.reports import REPORT_TYPES

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Daily HIS Report Automation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _summarize(values: dict) -> dict:
    return {
        "Bed Occupancy %": values.get("Occupancy %"),
        "OP Encounters": values.get("OP Encounters"),
        "Total Billing": values.get("Total Billing"),
        "AEPL Billing": values.get("AEPL Billing"),
    }


def _warnings_from_unmapped(unmapped: dict) -> list:
    warnings = []
    for label, values_list in unmapped.items():
        cleaned = [v for v in values_list if v is not None and str(v).strip().lower() != "nan"]
        if cleaned:
            sample = ", ".join(str(v) for v in cleaned[:3])
            more = f" (+{len(cleaned) - 3} more)" if len(cleaned) > 3 else ""
            warnings.append(
                f"{label}: {len(cleaned)} row(s) had a Category not found in Category Codes "
                f"(e.g. {sample}{more}) — excluded from category-based totals, needs manual review."
            )
    return warnings


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

    try:
        values, unmapped = run_pipeline(dataframes)
    except StageProcessingError as exc:
        return {"status": "error", "failed_file": exc.label, "reason": exc.reason}
    except Exception as exc:  # noqa: BLE001 - last-resort guard, still reported in plain language
        return {"status": "error", "failed_file": None, "reason": str(exc)}

    file_id = uuid.uuid4().hex
    work_dir = OUTPUT_DIR / file_id
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path = work_dir / "Final output.xlsx"

    write_final_output(
        template_path=BASE_DIR / "config" / "final_output_template.xlsx",
        output_path=output_path,
        values=values,
        date_column="F",
        report_date=report_date,
    )

    warnings = _warnings_from_unmapped(unmapped)

    return {
        "status": "warning" if warnings else "success",
        "summary": _summarize(values),
        "warnings": warnings,
        "download_url": f"/download/{file_id}",
    }


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
