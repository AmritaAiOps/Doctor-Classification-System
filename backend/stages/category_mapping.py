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

# Sentinel override value meaning "explicitly excluded" -- distinct from "no
# override at all". A value with this override is deliberately resolved to
# no bucket (won't count toward anything) and won't keep showing up in
# Category Review, since a human already made that call.
EXCLUDED = "__EXCLUDED__"


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def normalize_loose(value) -> str:
    """Aggressive normalization for fuzzy/override matching: strips ALL
    non-alphanumeric characters (not just whitespace), lowercased. Catches
    near-misses like "CPR25" vs "CPR-25" vs "CPR 25."
    """
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _load_map() -> dict:
    global _CATEGORY_MAP
    if not _CATEGORY_MAP:
        _CATEGORY_MAP = json.loads(CONFIG_PATH.read_text())
    return _CATEGORY_MAP


def map_category(raw_value: Optional[str]) -> Optional[str]:
    """Returns the internal bucket name (CPR, General, ECHS, TPA, P CARD FUND) or None.

    Pure lookup, no side effects -- callers that need to know what failed to
    match should use backend.stages.category_review instead of relying on
    this function to log anything.
    """
    if not raw_value or not isinstance(raw_value, str):
        return None
    entry = _load_map().get(_normalize(raw_value))
    if entry is None:
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


def resolve_category(raw_value: Optional[str], overrides: Optional[dict] = None) -> Optional[str]:
    """Same as map_category, but checks an override dict first.

    overrides is keyed by normalize_loose(raw_value) -> bucket (or EXCLUDED).
    These are corrections applied via the Category Review panel -- they are
    NEVER written back to config/category_map.json, the master Category
    Codes table. A value mapped to EXCLUDED resolves to None (same as
    unmatched) but is treated as already-reviewed, so it won't keep
    reappearing in Category Review.
    """
    if overrides and isinstance(raw_value, str):
        key = normalize_loose(raw_value)
        if key in overrides:
            value = overrides[key]
            return None if value == EXCLUDED else value
    return map_category(raw_value)


def is_overridden(raw_value: Optional[str], overrides: Optional[dict] = None) -> bool:
    """True if raw_value has an explicit override recorded (bucket or EXCLUDED)."""
    if not overrides or not isinstance(raw_value, str):
        return False
    return normalize_loose(raw_value) in overrides


def display_label(bucket: str) -> str:
    return DISPLAY_LABELS.get(bucket, bucket)
