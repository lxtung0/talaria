"""Group E, affiliation (spec #13, #18), tested only through `build_silver_facilities`.

`primary_affiliation` counts the raw `affiliationTypeIds` items in bronze, because
Silver base keeps each value once. The 8 allowed values always beat an Invalid
value (decided on #18), so `naac` can't win while an allowed value is there.
"""

import datetime
import json

import pytest

from talaria.silver_facilities import build_silver_facilities
from talaria.silver_facilities.checks import check_silver_facilities

RUN_DATE = datetime.date(2026, 11, 21)


@pytest.fixture
def build(make_silver_inputs, no_pincodes):
    """Silver facilities rows by `unique_id`, from partial bronze rows."""

    def run(*rows):
        bronze, silver_base = make_silver_inputs(*rows)
        facilities = build_silver_facilities(silver_base, bronze, no_pincodes, RUN_DATE)
        check_silver_facilities(silver_base, facilities)
        return {row.unique_id: row for row in facilities.collect()}

    return run


# Raw `affiliationTypeIds` items -> `primary_affiliation`.
PRIMARY = {
    "most frequent": (["government", "government", "academic"], "government"),
    "tie broken by D2": (["academic", "government"], "government"),
    "tie broken by D2, lower ranks": (["public", "corporate", "private"], "corporate"),
    "count beats rank": (["public", "public", "government"], "public"),
    "private-entity counts as private": (["community", "Private-Entity", "private"], "private"),
    "spelling variant counts toward its value": (["academic", "faith-tradition", "Faith Tradition"], "faith-tradition"),
    "case and whitespace": (["  ACADEMIC ", "academic", "government"], "academic"),
    "Invalid value never beats an allowed one": (["NAAC", "NAAC", "NAAC", "public"], "public"),
    "only Invalid values: most frequent": (["DCI", "NAAC", "naac"], "naac"),
    "only Invalid values: tie alphabetical": (["NAAC", "DCI"], "dci"),
    "Missing items ignored": (["null", "", "academic"], "academic"),
    "one value": (["philanthropy-legacy"], "philanthropy-legacy"),
}


def test_primary_affiliation(build):
    rows = build(*[{"unique_id": case, "affiliationTypeIds": json.dumps(raw)} for case, (raw, _) in PRIMARY.items()])

    assert {case: rows[case].primary_affiliation for case in PRIMARY} == {
        case: expected for case, (_, expected) in PRIMARY.items()
    }


@pytest.mark.parametrize("raw", [None, "[]", "null", '["", "null"]'])
def test_no_affiliations_is_null(build, raw):
    row = build({"affiliationTypeIds": raw})["facility-1"]

    assert row.affiliation_types is None
    assert row.primary_affiliation is None


def test_counts_come_from_each_facility_own_bronze_row(build):
    rows = build(
        {"unique_id": "a", "affiliationTypeIds": '["academic", "academic", "government"]'},
        {"unique_id": "b", "affiliationTypeIds": '["government", "government", "academic"]'},
    )

    assert (rows["a"].primary_affiliation, rows["b"].primary_affiliation) == ("academic", "government")


def test_description_fragments_and_exact_duplicates_in_bronze_dont_count(build):
    raw = '["academic", "government", "academic"]'
    rows = build(
        {"unique_id": "a", "affiliationTypeIds": '["government", "academic"]'},
        # A Description fragment sharing the id, and an exact duplicate row: Silver base drops both.
        {"unique_id": "a", "affiliationTypeIds": raw, "source_urls": None},
        {"unique_id": "b", "affiliationTypeIds": raw},
        {"unique_id": "b", "affiliationTypeIds": raw},
    )

    assert (rows["a"].primary_affiliation, rows["b"].primary_affiliation) == ("government", "academic")


# (raw affiliations, operator) -> flag_affiliation_operator_conflict.
CONFLICTS = [
    (["government"], "private", True),
    (["academic", "government"], "Private", True),
    (["private"], "public", True),
    (["corporate"], "government", True),  # Silver base turns operator `government` into `public`
    (["private-entity"], "public", True),
    (["government"], "public", False),
    (["private", "corporate"], "private", False),
    (["academic"], "private", False),
    (["government"], None, False),
    (None, "private", False),
    (None, None, False),
]


def test_affiliation_operator_conflict(build):
    rows = build(
        *[
            {
                "unique_id": str(i),
                "affiliationTypeIds": None if raw is None else json.dumps(raw),
                "operatorTypeId": operator,
            }
            for i, (raw, operator, _) in enumerate(CONFLICTS)
        ]
    )

    assert [rows[str(i)].flag_affiliation_operator_conflict for i in range(len(CONFLICTS))] == [
        expected for *_, expected in CONFLICTS
    ]
