"""Spec-facing adapter over the existing JSON daily-history store.

The spec asked for SQLite at backend/data/report_history.db, but a JSON store
(config/daily_history.json, stages/daily_history.py) already existed and is
what main.py writes on every run -- so per the spec's own instruction the
existing layer is extended instead. Records are keyed by metric name
internally; row-number dicts are translated via final_output.ROW_MAP.
"""
from backend.stages.daily_history import load_history, record_day, _is_valid_day_for_month
from backend.stages.final_output import ROW_MAP


def save_daily_snapshot(report_date, metric_values: dict) -> None:
    """metric_values: {final-output row number: value}. Re-saving a date
    overwrites that day (record_day semantics)."""
    values = {ROW_MAP[row]: v for row, v in metric_values.items() if row in ROW_MAP}
    record_day(report_date, values, metric_keys=list(values.keys()))


def _month_data(year: int, month: int) -> dict:
    return load_history().get(f"{year:04d}-{month:02d}", {})


def get_month_records(year: int, month: int) -> list:
    """One dict per recorded day: {"day": int, "values": {metric_key: value}}.

    Days that aren't actually valid calendar days for this month (a mis-filed
    or corrupted entry -- see daily_history._is_valid_day_for_month) are
    excluded, so finalize_month() never sums a wrong-month value into a
    completed month's figures.
    """
    month_str = f"{year:04d}-{month:02d}"
    month_data = _month_data(year, month)
    days = sorted({
        int(d) for series in month_data.values() for d in series
        if _is_valid_day_for_month(month_str, d)
    })
    return [
        {"day": day, "values": {k: s[str(day)] for k, s in month_data.items() if str(day) in s}}
        for day in days
    ]
