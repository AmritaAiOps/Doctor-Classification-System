import pandas as pd

from backend.stages.aepl_billing import process_aepl_billing, trace_aepl_billing_transactions


def test_process_aepl_billing_excludes_nn_and_np_and_computes_debit_minus_credit():
    df = pd.DataFrame({
        "AEPL Bill No": [
            "IPF/IPB_BC01/26/580",
            "IPF/NNBC01/26/581",
            "IPF/NPBC01/26/582",
            "OPD/IPB_BC01/26/915",
        ],
        "Posted Debit Amt": [1000, 5000, 3000, 500],
        "Posted Credit Amt": [200, 100, 50, 300],
    })
    result = process_aepl_billing(df)
    # Only rows 1 and 4 survive: debit (1000+500) - credit (200+300)
    assert result == 1000.0


def test_process_aepl_billing_case_insensitive_nn_np_match():
    df = pd.DataFrame({
        "AEPL Bill No": ["ipf/nnbc01/26/1", "ipf/npbc01/26/2", "ipf/ipb_bc01/26/3"],
        "Posted Debit Amt": [100, 200, 300],
        "Posted Credit Amt": [0, 0, 0],
    })
    result = process_aepl_billing(df)
    assert result == 300.0


def test_process_aepl_billing_returns_float_type():
    df = pd.DataFrame({
        "AEPL Bill No": ["IPF/IPB_BC01/26/580"],
        "Posted Debit Amt": [100],
        "Posted Credit Amt": [10],
    })
    result = process_aepl_billing(df)
    assert isinstance(result, float)
    assert result == 90.0


def test_process_aepl_billing_handles_real_column_name_variant():
    # Real sheet header is "Posted Debit Amount" / "Posted Credit Amount", not "Amt"
    df = pd.DataFrame({
        "AEPL Bill No": ["IPF/IPB_BC01/26/580", "IPF/NNBC01/26/581"],
        "Posted Debit Amount": [1000, 9999],
        "Posted Credit Amount": [100, 9999],
    })
    result = process_aepl_billing(df)
    assert result == 900.0


def test_trace_aepl_billing_transactions_marks_included_and_excluded_rows():
    df = pd.DataFrame({
        "AEPL Bill No": ["IPF/IPB_BC01/26/580", "IPF/NNBC01/26/581", "IPF/NPBC01/26/582"],
        "MRD": [111, 222, 333],
        "Posted Date": ["2026-07-20", "2026-07-20", "2026-07-20"],
        "Posted Debit Amount": [1000, 5000, 3000],
        "Posted Credit Amount": [200, 100, 50],
    })
    rows = trace_aepl_billing_transactions(df)
    assert len(rows) == 3

    included = rows[0]
    assert included["patient_id"] == 111
    assert included["net_amount"] == 800.0
    assert included["included"] is True
    assert included["exclusion_reason"] is None

    nn_row = rows[1]
    assert nn_row["included"] is False
    assert nn_row["exclusion_reason"] == "NN bill number"

    np_row = rows[2]
    assert np_row["included"] is False
    assert np_row["exclusion_reason"] == "NP bill number"

    # sum of included rows' net_amount must equal process_aepl_billing()'s total
    total = sum(r["net_amount"] for r in rows if r["included"])
    assert total == process_aepl_billing(df)


def test_trace_aepl_billing_transactions_tolerates_missing_optional_columns():
    df = pd.DataFrame({
        "AEPL Bill No": ["IPF/IPB_BC01/26/580"],
        "Posted Debit Amount": [100],
        "Posted Credit Amount": [10],
    })
    rows = trace_aepl_billing_transactions(df)
    assert rows[0]["patient_id"] is None
    assert rows[0]["posted_date"] is None
    assert rows[0]["net_amount"] == 90.0
