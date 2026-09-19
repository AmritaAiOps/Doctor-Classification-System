from backend.stages.reconciliation import check_reconciliation, run_daily_reconciliation


def test_check_reconciliation_within_tolerance_not_flagged():
    result = check_reconciliation("AEPL Billing", 11198483.0 + 5000, 11198483.0, tolerance_pct=0.1)
    assert result["flagged"] is False
    assert result["variance"] == 5000
    assert result["variance_pct"] < 0.1


def test_check_reconciliation_beyond_tolerance_is_flagged():
    # Matches the reported AEPL variance: 11,207,546 vs 11,198,483 (~0.08%)
    result = check_reconciliation("AEPL Billing", 11207546.0, 11198483.0, tolerance_pct=0.05)
    assert result["flagged"] is True
    assert result["variance"] == 9063.0


def test_check_reconciliation_ip_admission_case_from_ticket():
    result = check_reconciliation("IP Admission Total", 338, 200)
    assert result["flagged"] is True
    assert result["variance"] == 138
    assert result["variance_pct"] == 69.0


def test_check_reconciliation_missing_values_skipped_not_flagged():
    result = check_reconciliation("IP Discharges Total", None, 178)
    assert result["flagged"] is False
    assert result["note"] is not None


def test_check_reconciliation_zero_manual_value_nonzero_tool_value_flagged():
    result = check_reconciliation("Something", 5, 0)
    assert result["flagged"] is True
    assert result["variance_pct"] == 100.0


def test_check_reconciliation_zero_zero_is_clean():
    result = check_reconciliation("Something", 0, 0)
    assert result["flagged"] is False
    assert result["variance_pct"] == 0.0


def test_run_daily_reconciliation_only_checks_keys_with_a_manual_value():
    tool_values = {"IP Admission Total": 200, "IP Discharges Total": 178, "AEPL Billing": 11198483.0}
    manual_values = {"IP Admission Total": 200}
    report = run_daily_reconciliation(tool_values, manual_values)
    assert len(report["checks"]) == 1
    assert report["checks"][0]["label"] == "IP Admission Total"
    assert report["anyFlagged"] is False


def test_run_daily_reconciliation_flags_when_any_check_flags():
    tool_values = {"IP Admission Total": 338, "IP Discharges Total": 178}
    manual_values = {"IP Admission Total": 200, "IP Discharges Total": 178}
    report = run_daily_reconciliation(tool_values, manual_values)
    assert report["anyFlagged"] is True
    flagged_labels = [c["label"] for c in report["checks"] if c["flagged"]]
    assert flagged_labels == ["IP Admission Total"]
