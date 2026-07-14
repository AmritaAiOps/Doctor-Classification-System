"""Month-level averaging with the day-1 gate.

Rule (decided): a month whose day-1 snapshot was never recorded is never
averaged or projected -- its Daily Average / MTD columns stay "-" forever,
including the finalized 2-col block after rollover.
"""
import calendar

from backend import history_store
from backend.stages.mtd import AVERAGE_KEYS, CONSTANT_KEYS


def compute_month_column(report_date, metric_key: str = "Total Billing"):
    """Running numbers for the current 3-col block for one metric.
    Returns {"asOf", "dailyAverage", "mtdProjected"} or None when day 1 of
    the month was never recorded (or the metric has no data)."""
    year, month = report_date.year, report_date.month
    if not history_store.has_day_one(year, month):
        return None
    values = {
        rec["day"]: rec["values"][metric_key]
        for rec in history_store.get_month_records(year, month)
        if rec["day"] <= report_date.day and metric_key in rec["values"]
    }
    if not values:
        return None
    as_of = values.get(report_date.day)
    if metric_key in CONSTANT_KEYS:
        avg = proj = as_of
    elif metric_key in AVERAGE_KEYS:
        avg = sum(values.values()) / len(values)
        proj = avg  # snapshot metric: projecting a point-in-time reading is meaningless
    else:
        avg = sum(values.values()) / len(values)
        proj = avg * calendar.monthrange(year, month)[1]
    return {"asOf": as_of, "dailyAverage": avg, "mtdProjected": proj}


def finalize_month(year: int, month: int):
    """Static 2-col figures for a completed month:
    {metric_key: {"daily_avg", "mtd"}}, or None when day 1 was never recorded."""
    if not history_store.has_day_one(year, month):
        return None
    days_in_month = calendar.monthrange(year, month)[1]
    per_metric = {}
    for rec in history_store.get_month_records(year, month):
        for key, value in rec["values"].items():
            per_metric.setdefault(key, []).append(value)
    out = {}
    for key, vals in per_metric.items():
        if key in CONSTANT_KEYS:
            out[key] = {"daily_avg": vals[-1], "mtd": vals[-1]}
        elif key in AVERAGE_KEYS:
            avg = sum(vals) / len(vals)
            out[key] = {"daily_avg": avg, "mtd": avg}
        else:
            total = sum(vals)
            out[key] = {"daily_avg": total / days_in_month, "mtd": total}
    return out
