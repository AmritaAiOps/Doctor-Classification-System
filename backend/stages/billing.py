"""Stage 5: Billing OP + IP processing."""
import re

import pandas as pd

from backend.stages.category_mapping import resolve_category, map_region
from backend.stages.category_review import review_dataframe
from backend.stages.row_cleaning import strip_junk_rows


def _normalize_header(name) -> str:
    if not isinstance(name, str):
        return ""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _find_column(df: pd.DataFrame, expected_name: str, required: bool = True):
    """Matches a column whose normalized name starts with the normalized expected name.

    startswith (not equality) because real headers append suffixes like
    "(Inc.Tax)" or "(Inc. Tax)" onto "TotalAmt".
    """
    target = _normalize_header(expected_name)
    for col in df.columns:
        if _normalize_header(str(col)).startswith(target):
            return col
    if required:
        raise KeyError(f"Column matching {expected_name!r} not found. Available: {list(df.columns)}")
    return None


def _enrich(df: pd.DataFrame, overrides: dict = None) -> pd.DataFrame:
    total_amt_col = _find_column(df, "TotalAmt")
    disc_amt_col = _find_column(df, "DiscAmt")
    category_col = _find_column(df, "Category")

    df = df.copy()
    df["Net"] = pd.to_numeric(df[total_amt_col], errors="coerce") - pd.to_numeric(df[disc_amt_col], errors="coerce")
    df["CAT"] = df[category_col].map(lambda v: resolve_category(v, overrides))
    df["Cash_Credit"] = df["CAT"].map(lambda cat: "Cash" if cat == "General" else "Credit")
    df["Region"] = df[category_col].map(map_region)
    return df, category_col


def process_billing_op(df: pd.DataFrame, source_file: str = None, overrides: dict = None) -> tuple:
    total_amt_col = _find_column(df, "TotalAmt")
    disc_amt_col = _find_column(df, "DiscAmt")
    bill_type_col = _find_column(df, "BillType")

    cleaned, _dropped = strip_junk_rows(df, [total_amt_col, disc_amt_col])
    cleaned = cleaned.loc[cleaned[bill_type_col] == "O_B"]

    enriched, category_col = _enrich(cleaned, overrides)
    category_review = review_dataframe(enriched, category_col, source_file, overrides)
    return enriched, enriched["Net"].sum(), category_review


def process_billing_ip(df: pd.DataFrame, source_file: str = None, overrides: dict = None) -> tuple:
    total_amt_col = _find_column(df, "TotalAmt")
    disc_amt_col = _find_column(df, "DiscAmt")
    bill_type_col = _find_column(df, "BillType")

    cleaned, _dropped = strip_junk_rows(df, [total_amt_col, disc_amt_col])
    cleaned = cleaned.loc[cleaned[bill_type_col].isin(["IP_D", "IP_F"])]

    enriched, category_col = _enrich(cleaned, overrides)
    category_review = review_dataframe(enriched, category_col, source_file, overrides)

    time_col = _find_column(enriched, "Time", required=False)
    if time_col is not None:
        enriched = enriched.drop(columns=[time_col])

    return enriched, enriched["Net"].sum(), category_review
