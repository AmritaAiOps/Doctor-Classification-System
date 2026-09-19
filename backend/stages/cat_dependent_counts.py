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

# Patients still parked in the pre-ward holding area aren't real IP
# admissions/discharges yet per hospital policy, but the HIS export already
# tags them with a Category, so they'd otherwise inflate every bucket
# (General/TPA/ECHS/P.Card.Fund/Corporates) and the Total built from them.
EXCLUDED_WARD = "admissionward"


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


def _find_optional_column(df: pd.DataFrame, expected_name: str) -> str:
    """Same lookup as _find_column, but returns None instead of raising --
    used for columns (like Ward) whose absence should be tolerated rather
    than fail the whole stage."""
    target = _normalize_header(expected_name)
    for col in df.columns:
        if _normalize_header(str(col)) == target:
            return col
    return None


def _drop_admission_ward(df: pd.DataFrame) -> pd.DataFrame:
    ward_col = _find_optional_column(df, "Ward")
    if ward_col is None:
        return df
    normalized_ward = df[ward_col].astype(str).map(_normalize_header)
    return df.loc[normalized_ward != EXCLUDED_WARD]


def _process_cat_counts(df: pd.DataFrame, source_file: str = None, overrides: dict = None) -> dict:
    category_col = _find_column(df, "Category")
    df = _drop_admission_ward(df.copy())
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
