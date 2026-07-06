"""Stage 0.5: auto-detects which of the 9 required reports a given sheet is,
so staff can drop one combined workbook, 9 separate files, or any mix.

Detection order (highest confidence first), per the spec:
  1. Sheet name keyword match -- if exactly one report type's keywords appear
     in the (normalized) sheet name, that's a high-confidence match.
  2. Column-signature fallback -- if the sheet name is ambiguous or matches
     nothing, check the detected header row's columns against a known
     required/excluded keyword set per report type.
  3. Otherwise: undetected. Never silently guess -- surfaced to the frontend
     for manual assignment instead.
"""
import re

from backend.stages.reports import REPORT_TYPES

# report_type -> list of substrings; a sheet name normalized to alnum-lowercase
# matching ANY of these is considered a hit for that report type.
SHEET_NAME_KEYWORDS = {
    "Bed Occupancy": ["bedoccupancy"],
    "OP New Registration": ["opnewregistration", "newregistration"],
    "OP Encounters": ["opencounters"],
    "IP Admission": ["ipadmission"],
    "Admission Analysis": ["admissionanalysis"],
    "IP Discharges": ["ipdischarge"],
    "Billing INR OP": ["billinginrop"],
    "Billing INR IP": ["billinginrip"],
    "AEPL Billing": ["aepl"],
}

# report_type -> {"require": [...], "exclude": [...]}. All "require" keywords
# must appear as a substring of some normalized column name; none of the
# "exclude" keywords may appear in any column, to disambiguate near-identical
# sheets (e.g. Billing OP vs Billing IP both have TotalAmt/DiscAmt).
COLUMN_SIGNATURES = {
    "Bed Occupancy": {"require": ["bedstrength", "bedsoccupied"]},
    "OP New Registration": {"require": ["mrdnumber", "registrationdate"]},
    "OP Encounters": {"require": ["tokennumber", "loginid"]},
    "IP Admission": {"require": ["admitdate", "bedtype", "patientstatus"]},
    "Admission Analysis": {"require": ["totalemergencyadmission", "totalplannedadmission"]},
    "IP Discharges": {"require": ["dischargestatus", "sendforbillingtime"]},
    "Billing INR IP": {"require": ["totalamt", "discamt", "noofdaysadmitted"]},
    "Billing INR OP": {"require": ["totalamt", "discamt", "billtype"], "exclude": ["noofdaysadmitted"]},
    "AEPL Billing": {"require": ["aimsbillnumber", "posteddebit", "postedcredit"]},
}


def normalize_alnum(value) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def find_header_row(rows, max_scan: int = 10):
    """Picks the row (within the first max_scan rows) most likely to be a
    header: the one with the most non-blank string cells. Title rows (a
    single merged text cell) and data rows (numbers/dates) score lower."""
    best_idx, best_score = 0, -1
    scanned = list(rows)[:max_scan]
    for idx, row in enumerate(scanned):
        score = sum(1 for cell in row if isinstance(cell, str) and cell.strip())
        if score > best_score:
            best_score = score
            best_idx = idx
    header_row = scanned[best_idx] if scanned else []
    return best_idx, header_row


def _match_by_sheet_name(sheet_name: str):
    normalized = normalize_alnum(sheet_name)
    hits = [
        report_type
        for report_type, keywords in SHEET_NAME_KEYWORDS.items()
        if any(kw in normalized for kw in keywords)
    ]
    if len(hits) == 1:
        return hits[0]
    return None


def _match_by_columns(header_row):
    normalized_columns = [normalize_alnum(str(cell)) for cell in header_row if cell]
    for report_type, signature in COLUMN_SIGNATURES.items():
        required = signature.get("require", [])
        excluded = signature.get("exclude", [])
        if not all(any(req in col for col in normalized_columns) for req in required):
            continue
        if any(any(exc in col for col in normalized_columns) for exc in excluded):
            continue
        return report_type
    return None


def detect_report_type(sheet_name: str, rows) -> dict:
    """rows: the sheet's raw values (list of row tuples/lists), header=None,
    at least the first ~10 rows. Returns
    {report_type, confidence, matched_via, header_row}.
    """
    sheet_match = _match_by_sheet_name(sheet_name)
    if sheet_match:
        header_row_idx, _ = find_header_row(rows)
        return {
            "report_type": sheet_match,
            "confidence": "high",
            "matched_via": "sheet_name",
            "header_row": header_row_idx,
        }

    header_row_idx, header_row = find_header_row(rows)
    column_match = _match_by_columns(header_row)
    if column_match:
        return {
            "report_type": column_match,
            "confidence": "medium",
            "matched_via": "columns",
            "header_row": header_row_idx,
        }

    return {"report_type": None, "confidence": "none", "matched_via": None, "header_row": header_row_idx}
