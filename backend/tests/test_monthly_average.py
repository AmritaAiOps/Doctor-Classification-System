import datetime

import pytest

from backend import history_store
from backend.monthly_average import compute_month_column, finalize_month
from backend.stages import daily_history


@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_history, "HISTORY_PATH", tmp_path / "daily_history.json")


def _save(y, m, d, total_billing):
    history_store.save_daily_snapshot(datetime.date(y, m, d), {34: total_billing})


def test_snapshot_round_trip():
    _save(2026, 6, 1, 500.0)
    records = history_store.get_month_records(2026, 6)
    assert records == [{"day": 1, "values": {"Total Billing": 500.0}}]
    assert history_store.get_month_records(2026, 5) == []


def test_month_without_day_one_still_averages_recorded_days():
    _save(2026, 5, 18, 100.0)
    _save(2026, 5, 19, 100.0)
    col = compute_month_column(datetime.date(2026, 5, 19))
    assert col == {"asOf": 100.0, "dailyAverage": 100.0, "mtdProjected": 100.0 * 31}

    fin = finalize_month(2026, 5)
    assert fin["Total Billing"] == {"daily_avg": 200.0 / 31, "mtd": 200.0}


def test_month_with_no_recorded_days_returns_none():
    assert compute_month_column(datetime.date(2026, 5, 19)) is None
    assert finalize_month(2026, 5) is None


def test_running_average_and_projection():
    _save(2026, 6, 1, 100.0)
    col = compute_month_column(datetime.date(2026, 6, 1))
    assert col == {"asOf": 100.0, "dailyAverage": 100.0, "mtdProjected": 3000.0}

    _save(2026, 6, 2, 200.0)
    col = compute_month_column(datetime.date(2026, 6, 2))
    assert col["asOf"] == 200.0
    assert col["dailyAverage"] == 150.0
    assert col["mtdProjected"] == 150.0 * 30


def test_finalize_month_divides_sum_by_days_in_month():
    _save(2026, 6, 1, 100.0)
    _save(2026, 6, 2, 200.0)
    fin = finalize_month(2026, 6)
    assert fin["Total Billing"] == {"daily_avg": 300.0 / 30, "mtd": 300.0}
