"""Stage 8: Final output writer.

Writes computed values into the existing 'Final output' sheet at fixed rows,
in a single caller-specified date column. Every row is now resolved -- Long
Stay Patients (row 29) was the last one, computed from the IP Discharges file.
"""
import logging
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

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
    29: "Long Stay Patients",
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
    63: "Hospital Revenue (Net of AEPL)",
}

KEY_TO_ROW = {key: row for row, key in ROW_MAP.items()}

# Rows written as a live Excel formula referencing other rows in the SAME
# column, instead of a pre-computed number -- so opening the workbook shows
# staff exactly how the figure was derived. Row 63 = row 57 ("Total Billing"
# at the end of the Credit block) minus row 60 (AEPL Billing).
DERIVED_FORMULA_ROWS = {
    "Hospital Revenue (Net of AEPL)": ("Credit Total Billing", "AEPL Billing"),
}


def write_final_output(
    template_path, output_path, values: dict, date_column: str, report_date=None, mtd_columns: dict = None
) -> str:
    """mtd_columns: optional {row_key: {"daily_avg": ..., "mtd_proj": ...}}
    (see backend.stages.mtd.compute_mtd_columns). When given, writes Daily
    Average into the column right after date_column and MTD (Proj) into the
    one after that -- e.g. date_column="F" writes Daily Average to G and
    MTD (Proj) to H, matching the template's "As on" / "Daily Average" /
    "MTD (Proj)" column layout.
    """
    wb = openpyxl.load_workbook(template_path)
    ws = wb[SHEET_NAME]

    if report_date is not None:
        ws[f"{date_column}1"] = f"As on {report_date.strftime('%d %b %Y')}"

    date_col_idx = column_index_from_string(date_column)
    daily_avg_column = get_column_letter(date_col_idx + 1)
    mtd_proj_column = get_column_letter(date_col_idx + 2)

    for row, key in ROW_MAP.items():
        if key in DERIVED_FORMULA_ROWS:
            positive_key, negative_key = DERIVED_FORMULA_ROWS[key]
            if positive_key not in KEY_TO_ROW or negative_key not in KEY_TO_ROW:
                logger.warning("write_final_output: cannot build formula for %r; missing row mapping.", key)
                continue
            positive_row, negative_row = KEY_TO_ROW[positive_key], KEY_TO_ROW[negative_key]

            ws[f"{date_column}{row}"] = f"={date_column}{positive_row}-{date_column}{negative_row}"
            if mtd_columns:
                ws[f"{daily_avg_column}{row}"] = f"={daily_avg_column}{positive_row}-{daily_avg_column}{negative_row}"
                ws[f"{mtd_proj_column}{row}"] = f"={mtd_proj_column}{positive_row}-{mtd_proj_column}{negative_row}"
            continue

        if key not in values:
            logger.warning("write_final_output: missing value for %r (row %d); leaving cell untouched.", key, row)
            continue
        ws[f"{date_column}{row}"] = values[key]

        if mtd_columns and key in mtd_columns:
            ws[f"{daily_avg_column}{row}"] = mtd_columns[key]["daily_avg"]
            ws[f"{mtd_proj_column}{row}"] = mtd_columns[key]["mtd_proj"]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return str(output_path)
