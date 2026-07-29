"""Stage 7: AEPL Billing."""
import re

import pandas as pd


def _normalize_header(name) -> str:
    if not isinstance(name, str):
        return ""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _find_column(df: pd.DataFrame, expected_name: str) -> str:
    """Matches a column whose normalized name contains the normalized expected name.

    Uses "contains" (not exact/prefix) because real headers vary the suffix,
    e.g. "Posted Debit Amt" vs the actual "Posted Debit Amount".
    """
    target = _normalize_header(expected_name)
    for col in df.columns:
        if target in _normalize_header(str(col)):
            return col
    raise ValueError(f"Column matching {expected_name!r} not found. Available: {list(df.columns)}")


def process_aepl_billing(df: pd.DataFrame) -> float:
    bill_number_col = _find_column(df, "AEPL Bill No")
    debit_col = _find_column(df, "Posted Debit")
    credit_col = _find_column(df, "Posted Credit")

    bill_number = df[bill_number_col].astype(str).str.upper()
    excluded = bill_number.str.contains("NN") | bill_number.str.contains("NP")
    cleaned = df.loc[~excluded]

    debit_sum = pd.to_numeric(cleaned[debit_col], errors="coerce").sum()
    credit_sum = pd.to_numeric(cleaned[credit_col], errors="coerce").sum()
    return float(debit_sum - credit_sum)
