"""Persists each day's Final output values so MTD (month-to-date) and Daily
Average can be computed for the current month.

This app processes one day at a time and has no other memory of past days,
so true MTD (a running sum from the 1st of the month) requires remembering
every day already processed this month. That's what this store is for --
distinct from config/category_map.json and config/learned_overrides.json,
which are about category mapping, not daily figures.

Note: MTD/Daily Average will only reflect days actually processed through
this app. A month that started before this tool was in use will show a
partial MTD (missing the days before tracking began), not the true
month-to-date total -- there's no way to backfill days we never received.
"""
import json
from pathlib import Path

from backend.runtime_paths import CONFIG_DIR

HISTORY_PATH = CONFIG_DIR / "daily_history.json"


def load_history() -> dict:
    if not HISTORY_PATH.exists():
        return {}
    return json.loads(HISTORY_PATH.read_text())


def save_history(history: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2, sort_keys=True))


def month_key(report_date) -> str:
    return report_date.strftime("%Y-%m")


def record_day(report_date, values: dict, metric_keys: list) -> dict:
    """Stores today's value for each of metric_keys under this month, keyed
    by day-of-month. Re-processing the same date overwrites that day's entry
    rather than double-counting it. Returns the updated history.
    """
    history = load_history()
    month = month_key(report_date)
    day = str(report_date.day)

    month_history = history.setdefault(month, {})
    for key in metric_keys:
        if key not in values:
            continue
        metric_series = month_history.setdefault(key, {})
        metric_series[day] = values[key]

    save_history(history)
    return history


def get_month_series(history: dict, report_date, metric_key: str) -> dict:
    """{day_of_month (int) -> value} for every day from the 1st through
    report_date that has a recorded value for metric_key. Missing days are
    simply absent (not assumed to be zero for display, but contribute
    nothing to a sum).
    """
    month = month_key(report_date)
    metric_series = history.get(month, {}).get(metric_key, {})
    return {
        int(day): value
        for day, value in metric_series.items()
        if int(day) <= report_date.day
    }
