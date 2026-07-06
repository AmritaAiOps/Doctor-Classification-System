from backend.stages import category_mapping as cm


def test_domestic_cpr():
    assert cm.map_category("CPR") == "CPR"
    assert cm.map_region("CPR") == "Domestic"


def test_domestic_general_variant_case_and_space_insensitive():
    assert cm.map_category("  gnl ") == "General"
    assert cm.map_region("GNL") == "Domestic"


def test_domestic_echs():
    assert cm.map_category("ECHS 2025") == "ECHS"
    assert cm.map_region("echs2025") == "Domestic"


def test_domestic_tpa():
    assert cm.map_category("TPA 24") == "TPA"
    assert cm.map_region("TPA 24") == "Domestic"


def test_domestic_p_card_fund():
    assert cm.map_category("P CARD FUND") == "P CARD FUND"
    assert cm.map_region("P CARD FUND") == "Domestic"


def test_international_cpr():
    assert cm.map_category("CPR - Oman") == "CPR"
    assert cm.map_region("CPR - Oman") == "International"


def test_international_general():
    assert cm.map_category("GNL - Oman") == "General"
    assert cm.map_region("GNL - Oman") == "International"


def test_international_tpa():
    assert cm.map_category("TPA-AASANDHA") == "TPA"
    assert cm.map_region("TPA-AASANDHA") == "International"


def test_unmapped_value_returns_none_and_is_logged():
    before = len(cm.unmapped_values)
    result = cm.map_category("Totally Unknown Category XYZ")
    assert result is None
    assert cm.map_region("Totally Unknown Category XYZ") is None
    assert len(cm.unmapped_values) == before + 1


def test_display_label_cpr_shows_as_corporates():
    assert cm.display_label("CPR") == "Corporates"
    assert cm.display_label("General") == "General"
