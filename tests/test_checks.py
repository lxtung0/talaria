"""Silver base runtime checks (spec #1, "Runtime checks"), tested through `check_silver_base`."""

import pytest

from talaria.silver_base import build_silver_base
from talaria.silver_base.checks import check_silver_base


def _silver(spark, rows):
    """A small Silver-base-shaped DataFrame: one text column and one list column."""
    return spark.createDataFrame(rows, "unique_id string, name string, specialties array<string>")


def test_real_silver_base_output_passes(make_bronze, no_pincodes):
    bronze = make_bronze(
        {"name": " null ", "specialties": '["", "cardiology", "Cardiology"]', "email": "[]"},
        {"name": "City Hospital", "phone_numbers": '["98765 43210"]'},
    )

    check_silver_base(build_silver_base(bronze, no_pincodes))


def test_null_unique_id_fails(spark):
    silver = _silver(spark, [("a", "A", None), (None, "B", None)])

    with pytest.raises(ValueError, match="unique_id is null in 1 row"):
        check_silver_base(silver)


def test_repeated_unique_id_fails(spark):
    silver = _silver(spark, [("a", "A", None), ("a", "B", None)])

    with pytest.raises(ValueError, match="unique_id is repeated"):
        check_silver_base(silver)


@pytest.mark.parametrize("spelling", ["null", "NULL", "", "[]", "write to [email protected]"])
def test_missing_value_spelling_in_a_text_column_fails(spark, spelling):
    silver = _silver(spark, [("a", spelling, None)])

    with pytest.raises(ValueError, match=r"name: 1 row\(s\) with a Missing-value spelling"):
        check_silver_base(silver)


@pytest.mark.parametrize("items", [["cardiology", None], ["cardiology", ""], ["null"]])
def test_empty_item_in_a_list_column_fails(spark, items):
    silver = _silver(spark, [("a", "A", items)])

    with pytest.raises(ValueError, match=r"specialties: 1 row\(s\) with an empty list item"):
        check_silver_base(silver)


def test_empty_array_in_a_list_column_fails(spark):
    silver = _silver(spark, [("a", "A", [])])

    with pytest.raises(ValueError, match=r"specialties: 1 row\(s\) with an empty list$"):
        check_silver_base(silver)


def test_every_failure_is_reported_together(spark):
    silver = _silver(spark, [("a", "null", []), ("a", "B", None)])

    with pytest.raises(ValueError) as failure:
        check_silver_base(silver)

    message = str(failure.value)
    assert "unique_id is repeated" in message
    assert "name: 1 row(s) with a Missing-value spelling" in message
    assert "specialties: 1 row(s) with an empty list" in message
