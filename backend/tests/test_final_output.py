import openpyxl
import pytest

from backend.stages.final_output import write_final_output, SHEET_NAME


@pytest.fixture
def template_path(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    ws["E4"] = "Bed Strength"
    ws["E5"] = "Beds Occupied"
    ws["E29"] = "Long Stay Patients"
    ws["E32"] = "OP"
    ws["F29"] = 999  # pre-existing value that must survive since row 29 is skipped
    path = tmp_path / "template.xlsx"
    wb.save(path)
    return path


def test_write_final_output_writes_known_rows(template_path, tmp_path):
    values = {
        "Bed Strength": 1000,
        "Beds Occupied": 966,
        "OP Billing": 9923868.6,
    }
    output_path = tmp_path / "output.xlsx"
    result_path = write_final_output(template_path, output_path, values, date_column="F")

    wb = openpyxl.load_workbook(result_path)
    ws = wb[SHEET_NAME]
    assert ws["F4"].value == 1000
    assert ws["F5"].value == 966
    assert ws["F32"].value == 9923868.6


def test_write_final_output_skips_unresolved_rows(template_path, tmp_path):
    values = {"Bed Strength": 1000}
    output_path = tmp_path / "output.xlsx"
    write_final_output(template_path, output_path, values, date_column="F")

    wb = openpyxl.load_workbook(output_path)
    ws = wb[SHEET_NAME]
    # Row 29 (Long Stay Patients) is not in ROW_MAP -- must be untouched
    assert ws["F29"].value == 999


def test_write_final_output_missing_key_leaves_cell_untouched(template_path, tmp_path):
    values = {}  # nothing supplied
    output_path = tmp_path / "output.xlsx"
    write_final_output(template_path, output_path, values, date_column="F")

    wb = openpyxl.load_workbook(output_path)
    ws = wb[SHEET_NAME]
    assert ws["F4"].value is None


def test_write_final_output_uses_given_date_column(template_path, tmp_path):
    values = {"Bed Strength": 1234}
    output_path = tmp_path / "output.xlsx"
    write_final_output(template_path, output_path, values, date_column="G")

    wb = openpyxl.load_workbook(output_path)
    ws = wb[SHEET_NAME]
    assert ws["G4"].value == 1234
    assert ws["F4"].value is None


def test_write_final_output_returns_output_path(template_path, tmp_path):
    output_path = tmp_path / "output.xlsx"
    result = write_final_output(template_path, output_path, {"Bed Strength": 1}, date_column="F")
    assert str(result) == str(output_path)
