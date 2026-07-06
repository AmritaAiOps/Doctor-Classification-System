"""Auto-detects the report date from uploaded sheets, so staff don't have to
type it in by hand every day (they can still override it if it's wrong).

Scans every column whose header contains "date" across all uploaded sheets,
parses whatever values are there, and returns the single most common date --
a daily HIS export is overwhelmingly one day's data, so the mode is a safe bet
even when a handful of stray dates (e.g. IP admit dates from prior days) are
mixed in.
"""
from collections import Counter

import pandas as pd

from backend.stages.detection import normalize_alnum


def detect_report_date(sheets: list) -> str:
    """sheets: list of (header_row_idx, rows) -- rows is the sheet's raw
    values (header=None), header_row_idx is the row index detect_report_type
    identified as the header. Returns an ISO date string, or None if no date
    could be found anywhere.
    """
    found_dates = []

    for header_row_idx, rows in sheets:
        if not rows or header_row_idx >= len(rows):
            continue
        header = rows[header_row_idx]
        date_col_indices = [i for i, cell in enumerate(header) if "date" in normalize_alnum(str(cell))]
        if not date_col_indices:
            continue

        for row in rows[header_row_idx + 1:]:
            for idx in date_col_indices:
                if idx >= len(row):
                    continue
                parsed = pd.to_datetime(row[idx], errors="coerce")
                if pd.notna(parsed):
                    found_dates.append(parsed.date())

    if not found_dates:
        return None

    most_common_date, _ = Counter(found_dates).most_common(1)[0]
    return most_common_date.isoformat()
