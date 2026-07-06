"""Stage 1: category-mapping engine.

Maps raw Category values from HIS exports to a fixed bucket
(CPR, General, ECHS, TPA, P CARD FUND) and region (Domestic/International),
using config/category_map.json built from the bundled Category Codes sheet.
"""
import json
import re
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "category_map.json"

DISPLAY_LABELS = {
    "CPR": "Corporates",
}

_CATEGORY_MAP: dict = {}
unmapped_values: list = []


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def _load_map() -> dict:
    global _CATEGORY_MAP
    if not _CATEGORY_MAP:
        _CATEGORY_MAP = json.loads(CONFIG_PATH.read_text())
    return _CATEGORY_MAP


def map_category(raw_value: Optional[str]) -> Optional[str]:
    """Returns the internal bucket name (CPR, General, ECHS, TPA, P CARD FUND) or None."""
    if not raw_value or not isinstance(raw_value, str):
        unmapped_values.append(raw_value)
        return None
    entry = _load_map().get(_normalize(raw_value))
    if entry is None:
        unmapped_values.append(raw_value)
        return None
    return entry["bucket"]


def map_region(raw_value: Optional[str]) -> Optional[str]:
    """Returns 'Domestic' or 'International' or None."""
    if not raw_value or not isinstance(raw_value, str):
        return None
    entry = _load_map().get(_normalize(raw_value))
    if entry is None:
        return None
    return entry["region"]


def display_label(bucket: str) -> str:
    return DISPLAY_LABELS.get(bucket, bucket)
