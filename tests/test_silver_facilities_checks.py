"""Silver facilities runtime checks and flag counts (spec #13), run on the public function's output."""

import datetime

import pytest
from pyspark.sql import functions as F

from talaria.silver_facilities import build_silver_facilities
from talaria.silver_facilities.checks import check_silver_facilities
from talaria.silver_facilities.flag_counts import flag_counts, format_flag_counts


@pytest.fixture
def tables(make_silver_inputs, no_pincodes):
    """`(silver_base, silver_facilities)` for two Facilities."""
    bronze, silver_base = make_silver_inputs(
        {"unique_id": "a", "name": "City Hospital", "recency_of_page_update": "3 weeks ago"},
        {"unique_id": "b", "phone_numbers": '["98765 43210"]'},
    )
    return silver_base, build_silver_facilities(silver_base, bronze, no_pincodes, datetime.date(2026, 11, 21))


def test_real_output_passes(tables):
    check_silver_facilities(*tables)


@pytest.mark.parametrize(
    "column, changed",
    [
        ("name", "'Other'"),  # a value, and NULL -> a value
        ("name", "CAST(NULL AS string)"),
        ("phone_numbers", "array('+919999999999')"),
        ("specialties", "CAST(array() AS array<string>)"),  # NULL -> empty list
        ("specialties", "array(CAST(NULL AS string))"),  # NULL -> list holding NULL
        ("_ingested_at", "_ingested_at + INTERVAL 1 MICROSECOND"),
    ],
)
def test_changed_column_fails(tables, column, changed):
    base, facilities = tables

    with pytest.raises(ValueError, match=rf"{column}: [12] row\(s\) changed from Silver base"):
        check_silver_facilities(base, facilities.withColumn(column, F.expr(changed)))


def test_null_flag_fails(tables):
    base, facilities = tables
    broken = facilities.withColumn("flag_future_page_update", F.lit(None).cast("boolean"))

    with pytest.raises(ValueError, match=r"flag_future_page_update: 2 row\(s\) with a NULL flag"):
        check_silver_facilities(base, broken)


def test_removed_row_fails(tables):
    base, facilities = tables

    with pytest.raises(ValueError, match="row count is 1, Silver base has 2"):
        check_silver_facilities(base, facilities.where("unique_id = 'a'"))


def test_repeated_unique_id_fails(tables):
    base, facilities = tables

    with pytest.raises(ValueError, match="unique_id is repeated"):
        check_silver_facilities(base, facilities.unionByName(facilities))


def test_null_unique_id_fails(tables):
    base, facilities = tables
    broken = facilities.withColumn("unique_id", F.expr("nullif(unique_id, 'b')"))

    with pytest.raises(ValueError, match="unique_id is null in 1 row"):
        check_silver_facilities(base, broken)


def test_replaced_unique_id_fails(tables):
    base, facilities = tables
    broken = facilities.replace("b", "c", subset=["unique_id"])

    with pytest.raises(ValueError, match="unique_id differs from Silver base: 1 lost, 1 added"):
        check_silver_facilities(base, broken)


@pytest.mark.parametrize(
    "tamper, message",
    [
        (lambda df: df.drop("name"), "name: column is missing"),
        (lambda df: df.drop("flag_future_page_update"), "flag_future_page_update: column is missing"),
        (lambda df: df.withColumn("bed_count", F.expr("bigint(bed_count)")), "bed_count: type is bigint, expected int"),
        (
            lambda df: df.withColumn("flag_future_page_update", F.lit("false")),
            "flag_future_page_update: type is string, expected boolean",
        ),
        (lambda df: df.withColumn("page_date", F.current_date()), "page_date: unexpected column"),
    ],
)
def test_wrong_schema_fails(tables, tamper, message):
    base, facilities = tables

    with pytest.raises(ValueError, match=message):
        check_silver_facilities(base, tamper(facilities))


def test_counts_true_and_false_per_flag(tables):
    counts = flag_counts(tables[1])

    assert counts["flag_page_update_unparsable"] == {"true": 1, "false": 1}
    assert counts["flag_future_page_update"] == {"true": 0, "false": 2}
    assert "flag_page_update_unparsable" in format_flag_counts(counts)
