from config import SILVER, SILVER_BASE


def test_silver_base_facilities_has_its_own_table_name():
    assert SILVER_BASE["facilities"] == "workspace.talaria.silver_facilities_base"


def test_silver_facilities_has_its_own_table_name():
    assert SILVER["facilities"] == "workspace.talaria.silver_facilities"


def test_app_tables_are_all_app_prefixed():
    from config import APP, APP_VS_INDEX

    assert all(name.startswith("workspace.talaria.app_") for name in [*APP.values(), APP_VS_INDEX])
