from config import SILVER, SILVER_BASE, SILVER_STAGE3


def test_silver_base_facilities_has_its_own_table_name():
    assert SILVER_BASE["facilities"] == "workspace.talaria.silver_facilities_base"


def test_silver_facilities_has_its_own_table_name():
    assert SILVER["facilities"] == "workspace.talaria.silver_facilities"


def test_silver_stage3_has_its_own_table_names():
    assert SILVER_STAGE3 == {
        "facilities": "workspace.talaria.silver_facilities_stage3",
        "rule_counts": "workspace.talaria.silver_stage3_rule_counts",
    }
