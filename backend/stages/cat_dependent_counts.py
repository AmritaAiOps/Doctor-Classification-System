"""Stage 4: CAT-dependent counts for IP Admission and IP Discharges."""
import re

import pandas as pd

from backend.stages.category_mapping import resolve_category
from backend.stages.category_review import review_dataframe

BUCKET_TO_OUTPUT_KEY = {
    "General": "General",
    "TPA": "TPA",
    "ECHS": "ECHS",
    "P CARD FUND": "P.Card.Fund",
    "CPR": "Corporates",
}


def _normalize_header(name) -> str:
    if not isinstance(name, str):
        return ""
    return re.sub(r"\s+", "", name.strip().lower())


def _find_column(df: pd.DataFrame, expected_name: str) -> str:
    target = _normalize_header(expected_name)
    for col in df.columns:
        if _normalize_header(str(col)) == target:
            return col
    raise ValueError(f"Column matching {expected_name!r} not found. Available: {list(df.columns)}")


def _process_cat_counts(df: pd.DataFrame, source_file: str = None, overrides: dict = None) -> dict:
    category_col = _find_column(df, "Category")
    df = df.copy()
    df["CAT"] = df[category_col].map(lambda v: resolve_category(v, overrides))

    result = {}
    for bucket, output_key in BUCKET_TO_OUTPUT_KEY.items():
        result[output_key] = int((df["CAT"] == bucket).sum())

    result["Total"] = sum(result.values())
    result["category_review"] = review_dataframe(df, category_col, source_file, overrides)
    return result


def process_ip_admission(df: pd.DataFrame, source_file: str = None, overrides: dict = None) -> dict:
    return _process_cat_counts(df, source_file, overrides)


def process_ip_discharges(df: pd.DataFrame, source_file: str = None, overrides: dict = None) -> dict:
    return _process_cat_counts(df, source_file, overrides)
