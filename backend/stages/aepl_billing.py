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


def _find_optional_column(df: pd.DataFrame, expected_name: str) -> str:
    target = _normalize_header(expected_name)
    for col in df.columns:
        if target in _normalize_header(str(col)):
            return col
    return None


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


def trace_aepl_billing_transactions(df: pd.DataFrame) -> list:
    """Per-transaction breakdown of exactly what process_aepl_billing() summed,
    for manual reconciliation against the AEPL/AIMS source ledger.

    Every row from the input is included (with an `included` flag showing
    whether it fed the total, and `exclusion_reason` when it didn't), rather
    than only the rows that counted -- an analyst reconciling a variance needs
    to see the excluded NN/NP rows too, to confirm they really were meant to
    drop out.
    """
    bill_number_col = _find_column(df, "AEPL Bill No")
    debit_col = _find_column(df, "Posted Debit")
    credit_col = _find_column(df, "Posted Credit")
    mrd_col = _find_optional_column(df, "MRD")
    date_col = _find_optional_column(df, "Posted Date")

    bill_number = df[bill_number_col].astype(str).str.upper()
    is_nn = bill_number.str.contains("NN")
    is_np = bill_number.str.contains("NP")
    debit = pd.to_numeric(df[debit_col], errors="coerce")
    credit = pd.to_numeric(df[credit_col], errors="coerce")

    rows = []
    for idx in df.index:
        excluded = bool(is_nn[idx] or is_np[idx])
        reason = None
        if is_nn[idx]:
            reason = "NN bill number"
        elif is_np[idx]:
            reason = "NP bill number"
        rows.append({
            "row": int(idx),
            "patient_id": df.at[idx, mrd_col] if mrd_col else None,
            "bill_number": df.at[idx, bill_number_col],
            "posted_debit": None if pd.isna(debit[idx]) else float(debit[idx]),
            "posted_credit": None if pd.isna(credit[idx]) else float(credit[idx]),
            "net_amount": None if (pd.isna(debit[idx]) and pd.isna(credit[idx]))
                          else float((0 if pd.isna(debit[idx]) else debit[idx])
                                     - (0 if pd.isna(credit[idx]) else credit[idx])),
            "posted_date": df.at[idx, date_col] if date_col else None,
            "included": not excluded,
            "exclusion_reason": reason,
        })
    return rows
