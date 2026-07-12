import datetime

from backend.stages.mtd import compute_mtd_columns, CUMULATIVE_KEYS, AVERAGE_KEYS, CONSTANT_KEYS


def test_cumulative_metric_uses_true_mtd_sum_divided_by_day():
    report_date = datetime.date(2026, 6, 18)
    history = {
        "2026-06": {
            "OP Encounters": {str(d): 200 for d in range(1, 18)},  # days 1-17
        }
    }
    values = {"OP Encounters": 3744}  # today's (day 18) figure
    # get_month_series only includes days already in history for days<=18;
    # day 18 itself isn't in history yet at call time, so seed it via values
    # through record_day in real usage -- here we test the raw math directly
    # by injecting day 18 into history to mirror what main.py does.
    history["2026-06"]["OP Encounters"]["18"] = 3744

    result = compute_mtd_columns(report_date, values, history)
    mtd_actual = 200 * 17 + 3744
    assert result["OP Encounters"]["daily_avg"] == mtd_actual / 18
    assert result["OP Encounters"]["mtd_proj"] == (mtd_actual / 18) * 30


def test_average_metric_averages_days_not_sums():
    report_date = datetime.date(2026, 6, 3)
    history = {
        "2026-06": {
            "Beds Occupied": {"1": 900, "2": 950, "3": 1028},
        }
    }
    values = {"Beds Occupied": 1028}
    result = compute_mtd_columns(report_date, values, history)
    expected_avg = (900 + 950 + 1028) / 3
    assert result["Beds Occupied"]["daily_avg"] == expected_avg
    assert result["Beds Occupied"]["mtd_proj"] == expected_avg  # no *days_in_month scaling


def test_average_metric_falls_back_to_todays_value_with_no_history():
    report_date = datetime.date(2026, 6, 1)
    values = {"Occupancy %": 0.966}
    result = compute_mtd_columns(report_date, values, history={})
    assert result["Occupancy %"]["daily_avg"] == 0.966
    assert result["Occupancy %"]["mtd_proj"] == 0.966


def test_constant_metric_carries_value_forward_unchanged():
    report_date = datetime.date(2026, 6, 18)
    values = {"Bed Strength": 1000}
    result = compute_mtd_columns(report_date, values, history={})
    assert result["Bed Strength"] == {"daily_avg": 1000, "mtd_proj": 1000}


def test_hospital_revenue_derived_from_row57_minus_aepl_in_every_column():
    # Row 63 = row 57 ("Total Billing" at the end of the Credit block, our
    # internal key "Credit Total Billing") minus row 60 (AEPL Billing).
    report_date = datetime.date(2026, 6, 18)
    history = {
        "2026-06": {
            "Credit Total Billing": {"18": 8742193.15},
            "AEPL Billing": {"18": 9667188.25},
        }
    }
    values = {
        "Credit Total Billing": 8742193.15,
        "AEPL Billing": 9667188.25,
        "Hospital Revenue (Net of AEPL)": 8742193.15 - 9667188.25,
    }
    result = compute_mtd_columns(report_date, values, history)

    expected_daily_avg = result["Credit Total Billing"]["daily_avg"] - result["AEPL Billing"]["daily_avg"]
    expected_mtd_proj = result["Credit Total Billing"]["mtd_proj"] - result["AEPL Billing"]["mtd_proj"]
    assert result["Hospital Revenue (Net of AEPL)"]["daily_avg"] == expected_daily_avg
    assert result["Hospital Revenue (Net of AEPL)"]["mtd_proj"] == expected_mtd_proj


def test_missing_value_key_is_skipped_not_crashed():
    report_date = datetime.date(2026, 6, 18)
    result = compute_mtd_columns(report_date, values={}, history={})
    assert result == {}


def test_row_map_keys_fully_partitioned_no_overlap():
    overlap = (CUMULATIVE_KEYS & AVERAGE_KEYS) | (CUMULATIVE_KEYS & CONSTANT_KEYS) | (AVERAGE_KEYS & CONSTANT_KEYS)
    assert overlap == set()
