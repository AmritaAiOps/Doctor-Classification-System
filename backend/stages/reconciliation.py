"""Stage 14: tool-output vs. manual/source-ledger reconciliation.

Distinct from backend.verification, which checks the pipeline's internal
arithmetic against itself (row totals add up, nothing is negative). This
module checks the pipeline's *output* against a number that came from
somewhere else entirely -- a manually compiled figure, or a source ledger
total -- which is the only way to catch a bug that is internally consistent
but still wrong (e.g. the Admission Ward rows that inflated IP Admission/IP
Discharges: every internal reconciliation still balanced, because the bug
was in what got counted, not in the addition).

Soft by design, same as verification: a mismatch is reported, never raised,
so a missing/late manual figure can't block the daily statement.
"""
from typing import Optional

DEFAULT_TOLERANCE_PCT = 0.1  # percent; e.g. 0.1 == flag anything over 0.1%

# The three heads this was written for, but check_reconciliation() works for
# any (tool_value, manual_value) pair -- this list is just the default set
# run_daily_reconciliation() checks when the caller doesn't pass its own.
DEFAULT_KEYS = ["IP Admission Total", "IP Discharges Total", "AEPL Billing"]


def check_reconciliation(
    label: str,
    tool_value: Optional[float],
    manual_value: Optional[float],
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> dict:
    """Compares one tool-computed figure against one manual/source figure.

    variance_pct is relative to manual_value (the presumed ground truth),
    except when manual_value is 0 -- then any nonzero tool_value is a 100%
    miss and a zero/zero pair is a clean match, to avoid a division by zero
    hiding a real discrepancy.
    """
    if tool_value is None or manual_value is None:
        return {
            "label": label, "tool_value": tool_value, "manual_value": manual_value,
            "variance": None, "variance_pct": None, "tolerance_pct": tolerance_pct,
            "flagged": False, "note": "missing tool_value or manual_value; skipped",
        }

    tool_value = float(tool_value)
    manual_value = float(manual_value)
    variance = tool_value - manual_value

    if manual_value == 0:
        variance_pct = 0.0 if tool_value == 0 else 100.0
    else:
        variance_pct = abs(variance) / abs(manual_value) * 100

    return {
        "label": label,
        "tool_value": tool_value,
        "manual_value": manual_value,
        "variance": variance,
        "variance_pct": round(variance_pct, 4),
        "tolerance_pct": tolerance_pct,
        "flagged": variance_pct > tolerance_pct,
        "note": None,
    }


def run_daily_reconciliation(
    tool_values: dict,
    manual_values: dict,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    keys: Optional[list] = None,
) -> dict:
    """Runs check_reconciliation() for each key present in manual_values
    (defaulting to DEFAULT_KEYS), pulling the tool side from tool_values.

    Returns {"checks": [...], "anyFlagged": bool} -- same shape convention as
    backend.verification.run_verification, so a future combined report can
    merge the two lists directly.
    """
    keys = keys if keys is not None else DEFAULT_KEYS
    checks = [
        check_reconciliation(key, tool_values.get(key), manual_values.get(key), tolerance_pct)
        for key in keys
        if key in manual_values
    ]
    return {"checks": checks, "anyFlagged": any(c["flagged"] for c in checks)}
