import pandas as pd

from backend.stages.cat_dependent_counts import process_ip_admission, process_ip_discharges


def _sample_df():
    return pd.DataFrame({
        "MrdNo": [1, 2, 3, 4, 5, 6],
        "Category": ["GNL", "TPA", "ECHS", "P CARD FUND", "CPR", "Totally Unknown"],
    })


def test_process_ip_admission_counts_each_bucket_and_unmapped():
    df = _sample_df()
    result = process_ip_admission(df)
    assert result == {
        "General": 1,
        "TPA": 1,
        "ECHS": 1,
        "P.Card.Fund": 1,
        "Corporates": 1,
        "Total": 5,
        "unmapped": ["Totally Unknown"],
    }


def test_process_ip_discharges_same_shape_with_cate_gory_column():
    df = pd.DataFrame({
        "MrdNo": [1, 2, 3, 4, 5, 6],
        "Cate\ngory": ["GNL", "TPA", "ECHS", "P CARD FUND", "CPR", "Bogus"],
    })
    result = process_ip_discharges(df)
    assert result == {
        "General": 1,
        "TPA": 1,
        "ECHS": 1,
        "P.Card.Fund": 1,
        "Corporates": 1,
        "Total": 5,
        "unmapped": ["Bogus"],
    }


def test_process_ip_admission_handles_multiple_rows_per_bucket():
    df = pd.DataFrame({
        "Category": ["GNL", "GNL", "TPA", "GNL", "ECHS"],
    })
    result = process_ip_admission(df)
    assert result["General"] == 3
    assert result["TPA"] == 1
    assert result["ECHS"] == 1
    assert result["Corporates"] == 0
    assert result["P.Card.Fund"] == 0
    assert result["Total"] == 5
    assert result["unmapped"] == []
