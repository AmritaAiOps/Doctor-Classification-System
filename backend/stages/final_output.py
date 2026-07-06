"""Stage 8: Final output writer.

Writes computed values into the existing 'Final output' sheet at fixed rows,
in a single caller-specified date column. Rows 29, 63, 67-73 are intentionally
left blank -- their source logic is unresolved (Stage 9, blocked on business input).
"""
import logging
from pathlib import Path

import openpyxl

logger = logging.getLogger(__name__)

SHEET_NAME = "Final output"

# row number -> key expected in the `values` dict passed to write_final_output
ROW_MAP = {
    4: "Bed Strength",
    5: "Beds Occupied",
    6: "Occupancy %",
    9: "OP New Registration",
    10: "OP Encounters",
    11: "IP Admission Total",
    12: "IP Admission General",
    13: "IP Admission TPA",
    14: "IP Admission ECHS",
    15: "IP Admission P.Card.Fund",
    16: "IP Admission Corporates",
    18: "Emergency Admission",
    19: "Planned Admission",
    20: "Admission from OP (walk-in)",
    22: "IP Discharges Total",
    23: "IP Discharges General",
    24: "IP Discharges TPA",
    25: "IP Discharges ECHS",
    26: "IP Discharges P.Card.Fund",
    27: "IP Discharges Corporates",
    # 29: Long Stay Patients -- SKIP (unresolved)
    32: "OP Billing",
    33: "IP Billing",
    34: "Total Billing",
    37: "Billing Domestic",
    38: "Billing International",
    39: "Billing Total",
    44: "Cash Domestic",
    45: "Cash International",
    48: "Credit Domestic Total",
    49: "Credit Domestic ECHS",
    50: "Credit Domestic P.Card.Fund",
    51: "Credit Domestic TPA",
    52: "Credit Domestic Corporates",
    54: "Credit International Total",
    55: "Credit International TPA Aasantha",
    56: "Credit International Corporates (International)",
    57: "Credit Total Billing",
    60: "AEPL Billing",
    # 63: Hospital Revenue (Net of AEPL) -- SKIP (unresolved)
    # 67-73: Collection block -- SKIP (unresolved)
}


def write_final_output(template_path, output_path, values: dict, date_column: str, report_date=None) -> str:
    wb = openpyxl.load_workbook(template_path)
    ws = wb[SHEET_NAME]

    if report_date is not None:
        ws[f"{date_column}1"] = f"As on {report_date.strftime('%d %b %Y')}"

    for row, key in ROW_MAP.items():
        if key not in values:
            logger.warning("write_final_output: missing value for %r (row %d); leaving cell untouched.", key, row)
            continue
        ws[f"{date_column}{row}"] = values[key]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return str(output_path)
