import datetime

import backend.stages.daily_history as dh


def test_load_history_returns_empty_dict_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dh, "HISTORY_PATH", tmp_path / "missing.json")
    assert dh.load_history() == {}


def test_record_day_then_get_month_series(tmp_path, monkeypatch):
    monkeypatch.setattr(dh, "HISTORY_PATH", tmp_path / "history.json")

    d1 = datetime.date(2026, 6, 1)
    d2 = datetime.date(2026, 6, 2)
    dh.record_day(d1, {"OP Encounters": 100}, ["OP Encounters"])
    dh.record_day(d2, {"OP Encounters": 150}, ["OP Encounters"])

    history = dh.load_history()
    series = dh.get_month_series(history, d2, "OP Encounters")
    assert series == {1: 100, 2: 150}


def test_record_day_overwrites_same_day_not_double_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(dh, "HISTORY_PATH", tmp_path / "history.json")

    d = datetime.date(2026, 6, 5)
    dh.record_day(d, {"OP Encounters": 100}, ["OP Encounters"])
    dh.record_day(d, {"OP Encounters": 999}, ["OP Encounters"])  # re-processed, corrected

    history = dh.load_history()
    series = dh.get_month_series(history, d, "OP Encounters")
    assert series == {5: 999}


def test_get_month_series_excludes_days_after_report_date(tmp_path, monkeypatch):
    monkeypatch.setattr(dh, "HISTORY_PATH", tmp_path / "history.json")

    dh.record_day(datetime.date(2026, 6, 1), {"X": 1}, ["X"])
    dh.record_day(datetime.date(2026, 6, 20), {"X": 99}, ["X"])

    history = dh.load_history()
    series = dh.get_month_series(history, datetime.date(2026, 6, 10), "X")
    assert series == {1: 1}  # day 20 is in the future relative to day 10


def test_get_month_series_scoped_to_month():
    history = {
        "2026-05": {"OP Encounters": {"31": 500}},
        "2026-06": {"OP Encounters": {"1": 100}},
    }
    series = dh.get_month_series(history, datetime.date(2026, 6, 1), "OP Encounters")
    assert series == {1: 100}


def test_record_day_ignores_keys_missing_from_values(tmp_path, monkeypatch):
    monkeypatch.setattr(dh, "HISTORY_PATH", tmp_path / "history.json")

    d = datetime.date(2026, 6, 1)
    dh.record_day(d, {"OP Encounters": 100}, ["OP Encounters", "Nonexistent Key"])

    history = dh.load_history()
    assert "Nonexistent Key" not in history["2026-06"]
