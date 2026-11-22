"""Silver facilities behaviour, tested only through `build_silver_facilities` (spec #13, Testing Decisions)."""

import datetime

import pytest

from talaria.silver_facilities import build_silver_facilities

RUN_DATE = datetime.date(2026, 11, 21)


@pytest.fixture
def build(make_silver_inputs, no_pincodes):
    """Silver facilities rows by `unique_id`, from partial bronze rows."""

    def run(*rows):
        bronze, silver_base = make_silver_inputs(*rows)
        facilities = build_silver_facilities(silver_base, bronze, no_pincodes, RUN_DATE)
        return {row.unique_id: row for row in facilities.collect()}

    return run


def test_keeps_every_row_and_silver_base_column_unchanged(make_silver_inputs, no_pincodes):
    bronze, silver_base = make_silver_inputs(
        {"name": "City Hospital", "phone_numbers": '["98765 43210"]', "recency_of_page_update": "3 weeks ago"},
        {},
    )

    facilities = build_silver_facilities(silver_base, bronze, no_pincodes, RUN_DATE)

    assert facilities.columns[: len(silver_base.columns)] == silver_base.columns
    kept = facilities.select(*silver_base.columns)
    assert kept.schema.simpleString() == silver_base.schema.simpleString()
    assert sorted(kept.collect(), key=lambda r: r.unique_id) == sorted(silver_base.collect(), key=lambda r: r.unique_id)


def test_adds_only_the_new_columns(make_silver_inputs, no_pincodes):
    bronze, silver_base = make_silver_inputs({})

    facilities = build_silver_facilities(silver_base, bronze, no_pincodes, RUN_DATE)

    assert facilities.dtypes[len(silver_base.columns) :] == [
        ("flag_affiliation_operator_conflict", "boolean"),
        ("primary_affiliation", "string"),
        ("flag_page_update_unparsable", "boolean"),
        ("flag_future_page_update", "boolean"),
    ]


# G. Page update date: value -> (unparsable, future).
PAGE_DATES = {
    "2025-10-01": (False, False),
    "2024-02-29": (False, False),
    "October 2025": (False, False),  # Silver base rewrites it to ISO
    "2026-11-20": (False, False),
    "2026-11-21": (False, False),  # the run date itself
    "2026-11-22": (False, True),
    "3 weeks ago": (True, False),
    "2025-13-40": (True, False),
    "2025-02-29": (True, False),
    "2025": (True, False),
    "2099": (True, False),
    "2025-10": (True, False),
    "2025-1-5": (True, False),
    "2099-01-01T00:00:00": (True, False),
    None: (False, False),
}


@pytest.mark.parametrize("ansi", ["false", "true"])
def test_page_date_flags(build, spark, ansi):
    # Databricks runs with ANSI mode on, where a bad cast raises.
    previous = spark.conf.get("spark.sql.ansi.enabled", "false")
    spark.conf.set("spark.sql.ansi.enabled", ansi)
    try:
        rows = build(*[{"unique_id": str(value), "recency_of_page_update": value} for value in PAGE_DATES])
    finally:
        spark.conf.set("spark.sql.ansi.enabled", previous)

    actual = {
        value: (rows[str(value)].flag_page_update_unparsable, rows[str(value)].flag_future_page_update)
        for value in PAGE_DATES
    }
    assert actual == PAGE_DATES


def test_future_depends_on_the_run_date_passed_in(make_silver_inputs, no_pincodes):
    bronze, silver_base = make_silver_inputs({"recency_of_page_update": "2025-10-01"})

    facilities = build_silver_facilities(silver_base, bronze, no_pincodes, datetime.date(2025, 9, 30))

    assert facilities.first().flag_future_page_update is True
