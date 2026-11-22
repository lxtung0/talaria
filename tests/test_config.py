from config import GOLD, SILVER, SILVER_BASE, SILVER_FACILITY_DISTRICTS, SILVER_STAGE3


def test_silver_base_facilities_has_its_own_table_name():
    assert SILVER_BASE["facilities"] == "workspace.talaria.silver_facilities_base"


def test_silver_facilities_has_its_own_table_name():
    assert SILVER["facilities"] == "workspace.talaria.silver_facilities"


def test_silver_stage3_has_its_own_table_names():
    assert SILVER_STAGE3 == {
        "facilities": "workspace.talaria.silver_facilities_stage3",
        "rule_counts": "workspace.talaria.silver_stage3_rule_counts",
    }


def test_app_tables_are_all_app_prefixed():
    from config import APP, APP_VS_INDEX

    assert all(name.startswith("workspace.talaria.app_") for name in [*APP.values(), APP_VS_INDEX])


def test_silver_nfhs5_has_its_own_table_name():
    assert SILVER["nfhs5"] == "workspace.talaria.silver_nfhs5"


def test_facility_districts_has_its_own_table_name():
    assert SILVER_FACILITY_DISTRICTS == "workspace.talaria.silver_facility_districts"


def test_gold_tables_have_their_own_names():
    assert GOLD == {
        "facilities": "workspace.talaria.gold_facilities",
        "facility_items": "workspace.talaria.gold_facility_items",
    }
