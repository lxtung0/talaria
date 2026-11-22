from config import GOLD, SILVER, SILVER_BASE


def test_silver_base_facilities_has_its_own_table_name():
    assert SILVER_BASE["facilities"] == "workspace.talaria.silver_facilities_base"


def test_silver_facilities_has_its_own_table_name():
    assert SILVER["facilities"] == "workspace.talaria.silver_facilities"


def test_gold_tables_have_their_own_names():
    assert GOLD == {
        "facilities": "workspace.talaria.gold_facilities",
        "facility_items": "workspace.talaria.gold_facility_items",
    }
