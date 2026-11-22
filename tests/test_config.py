from config import SILVER, SILVER_BASE


def test_silver_base_facilities_has_its_own_table_name():
    assert SILVER_BASE["facilities"] == "workspace.talaria.silver_facilities_base"


def test_silver_facilities_name_stays_reserved_for_the_final_stage():
    assert SILVER["facilities"] == "workspace.talaria.silver_facilities"
