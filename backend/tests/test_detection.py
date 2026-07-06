import pandas as pd

from backend.stages.detection import detect_report_type, find_header_row
from backend.stages.reports import REPORT_TYPES


def _rows_from_header(header_cells, n_data_rows=2):
    rows = [header_cells]
    for _ in range(n_data_rows):
        rows.append([1] * len(header_cells))
    return rows


def test_sheet_name_match_high_confidence():
    result = detect_report_type("8.OP encounters", _rows_from_header(["A", "B"]))
    assert result["report_type"] == "OP Encounters"
    assert result["confidence"] == "high"
    assert result["matched_via"] == "sheet_name"


def test_sheet_name_ambiguous_falls_back_to_columns():
    # Generic sheet name "Sheet1" gives no keyword hit -> must fall back to columns
    rows = _rows_from_header(["Aims Bill Number", "Posted Debit Amount", "Posted Credit Amount"])
    result = detect_report_type("Sheet1", rows)
    assert result["report_type"] == "AEPL Billing"
    assert result["confidence"] == "medium"
    assert result["matched_via"] == "columns"


def test_no_match_returns_none_never_guesses():
    rows = _rows_from_header(["Random Column A", "Random Column B"])
    result = detect_report_type("Mystery Sheet", rows)
    assert result["report_type"] is None
    assert result["confidence"] == "none"


def test_disambiguates_billing_op_vs_ip_by_columns():
    op_rows = _rows_from_header(["Bill Type", "TotalAmt (Inc.Tax)", "Disc Amt", "Category"])
    ip_rows = _rows_from_header(["Bill Type", "Total Amt (Inc. Tax)", "Disc Amt", "No. of days Admitted"])

    op_result = detect_report_type("Sheet1", op_rows)
    ip_result = detect_report_type("Sheet2", ip_rows)

    assert op_result["report_type"] == "Billing INR OP"
    assert ip_result["report_type"] == "Billing INR IP"


def test_find_header_row_skips_title_row():
    rows = [
        ["Bed Type Wise Bed Occupancy Reports", None, None],
        ["Category", "Bed Strength", "Beds Occupied"],
        ["3 Bed Ward", 30, 25],
    ]
    idx, header = find_header_row(rows)
    assert idx == 1
    assert header == ["Category", "Bed Strength", "Beds Occupied"]


def test_all_9_report_types_have_sheet_keyword_or_signature():
    from backend.stages.detection import SHEET_NAME_KEYWORDS, COLUMN_SIGNATURES

    for report_type in REPORT_TYPES:
        assert report_type in SHEET_NAME_KEYWORDS or report_type in COLUMN_SIGNATURES


def test_detects_all_9_reports_from_real_sample_workbook():
    wb_path = "Daily report to automate.xlsx"
    sheet_to_expected = {
        "3.Bed occupancy": "Bed Occupancy",
        "7.OP new registration": "OP New Registration",
        "8.OP encounters": "OP Encounters",
        "16,17,18 Admission Analysis": "Admission Analysis",
        "IP Discharges 20,21,22,23,24,25": "IP Discharges",
        "IP Admission 9,10,11,12,13,14": "IP Admission",
        "Billing INR OP 30": "Billing INR OP",
        "Billing INR IP 31": "Billing INR IP",
        "AEPL Billing 58": "AEPL Billing",
    }
    xls = pd.ExcelFile(wb_path)
    detected = {}
    for sheet_name, expected_type in sheet_to_expected.items():
        raw = xls.parse(sheet_name=sheet_name, header=None, nrows=10)
        result = detect_report_type(sheet_name, raw.values.tolist())
        detected[expected_type] = result["report_type"]

    for expected_type in sheet_to_expected.values():
        assert detected[expected_type] == expected_type, f"failed to detect {expected_type}: got {detected[expected_type]}"

    # Non-report sheets must not be misdetected as one of the 9
    for extra_sheet in ["Category codes", "Final output"]:
        raw = xls.parse(sheet_name=extra_sheet, header=None, nrows=10)
        result = detect_report_type(extra_sheet, raw.values.tolist())
        assert result["report_type"] is None, f"{extra_sheet} was wrongly detected as {result['report_type']}"
