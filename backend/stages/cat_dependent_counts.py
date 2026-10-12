"""Stage 4: CAT-dependent counts for IP Admission and IP Discharges."""

import json

import pandas as pd

from backend.runtime_paths import CONFIG_DIR
from backend.stages.columns import find_column as _find_column
from backend.stages.category_mapping import resolve_category
from backend.stages.category_review import review_dataframe

BUCKET_TO_OUTPUT_KEY = {
    "General": "General",
    "TPA": "TPA",
    "ECHS": "ECHS",
    "P CARD FUND": "P.Card.Fund",
    "CPR": "Corporates",
}

def _process_cat_counts(df: pd.DataFrame, source_file: str = None, overrides: dict = None,
                        daycare_col: str = None, daycare_pattern: str = None) -> dict:
    category_col = _find_column(df, "Category")
    # footer/total rows have no Category -- not patients, keep them out of counts and review
    df = df.loc[df[category_col].notna()].copy()
    df["CAT"] = df[category_col].map(lambda v: resolve_category(v, overrides))

    # Day-care patients are reported separately, so they must not inflate General
    # (other buckets are unchanged -- matches the manual MIS figures).
    is_daycare = pd.Series(False, index=df.index)
    if daycare_col:
        col = _find_column(df, daycare_col, required=False)
        if col is not None:
            is_daycare = df[col].astype(str).str.contains(daycare_pattern, case=False, na=False)

    result = {}
    for bucket, output_key in BUCKET_TO_OUTPUT_KEY.items():
        result[output_key] = int(((df["CAT"] == bucket) & ~(is_daycare & (bucket == "General"))).sum())

    result["Total"] = sum(result.values())
    result["category_review"] = review_dataframe(df, category_col, source_file, overrides)
    return result


def _daycare_rule(report: str) -> tuple:
    # editable in config/daycare_rules.json: which column/pattern marks a day-care row
    rule = json.loads((CONFIG_DIR / "daycare_rules.json").read_text())[report]
    return rule["column"], rule["pattern"]


def process_ip_admission(df, source_file=None, overrides=None):
    return _process_cat_counts(df, source_file, overrides, *_daycare_rule("IP Admission"))


def process_ip_discharges(df, source_file=None, overrides=None):
    return _process_cat_counts(df, source_file, overrides, *_daycare_rule("IP Discharges"))
