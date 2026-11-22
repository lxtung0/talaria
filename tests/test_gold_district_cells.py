"""Gold district cells, tested through `build_district_cells` on small fake tables."""

import pytest

from talaria.district_link import office_districts
from talaria.district_link.aliases import DistrictAlias
from talaria.gold_districts import build_district_cells
from talaria.gold_districts.checks import check_district_cells

NFHS_SCHEMA = "state_ut string, district_name string, hh_member_covered_health_insurance_pct double, low_sample_columns array<string>"
NFHS = [
    ("Bihar", "Vaishali", 12.1, None),
    ("Bihar", "Patna", 18.4, ["hh_member_covered_health_insurance_pct"]),
    ("Andhra Pradesh", "Visakhapatnam", None, None),  # suppressed
]
OFFICE_SCHEMA = "pin string, office_lat double, office_lon double, nfhs_state string, nfhs_district string, approximate boolean, h3_r5 string"


@pytest.fixture
def nfhs(spark):
    return spark.createDataFrame(NFHS, NFHS_SCHEMA)


def _office(cell, state, district, approximate=False, lat=25.7, lon=85.2):
    return ("844101", lat, lon, state, district, approximate, cell)


@pytest.fixture
def cells(spark, nfhs):
    """`{h3_r5: row}` for offices `(cell, state, district[, approximate[, lat, lon]])`, after the checks pass."""

    def run(*offices):
        rows = [_office(*office) for office in offices]
        built = build_district_cells(spark.createDataFrame(rows, OFFICE_SCHEMA), nfhs)
        check_district_cells(nfhs, built)
        return {r.h3_r5: r.asDict() for r in built.collect()}

    return run


def test_a_cell_takes_the_district_most_of_its_offices_are_in(cells):
    rows = cells(("c1", "Bihar", "Vaishali"), ("c1", "Bihar", "Vaishali"), ("c1", "Bihar", "Patna"))

    assert rows["c1"] == {
        "h3_r5": "c1",
        "nfhs_state": "Bihar",
        "nfhs_district": "Vaishali",
        "district_share": 0.667,
        "district_approximate": False,
        "insurance_pct": 12.1,
        "insurance_pct_low_sample": False,
    }


def test_a_tie_goes_to_the_first_district_by_name(cells):
    assert cells(("c1", "Bihar", "Vaishali"), ("c1", "Bihar", "Patna"))["c1"]["nfhs_district"] == "Patna"


def test_low_sample_and_suppressed_indicators(cells):
    rows = cells(("c1", "Bihar", "Patna"), ("c2", "Andhra Pradesh", "Visakhapatnam"))

    assert (rows["c1"]["insurance_pct"], rows["c1"]["insurance_pct_low_sample"]) == (18.4, True)
    assert (rows["c2"]["insurance_pct"], rows["c2"]["insurance_pct_low_sample"]) == (None, False)


def test_an_approximate_office_makes_its_cell_approximate(cells):
    rows = cells(("c1", "Andhra Pradesh", "Visakhapatnam", True), ("c1", "Andhra Pradesh", "Visakhapatnam", False))

    assert rows["c1"]["district_approximate"] is True


def test_offices_outside_india_are_dropped(cells):
    rows = cells(("c1", "Bihar", "Patna", False, 0.0, 0.0), ("c2", "Bihar", "Patna"))

    assert set(rows) == {"c2"}


def test_office_districts_resolve_through_the_aliases(make_pincodes, nfhs):
    pincodes = make_pincodes((844101, "VAISHALI", "BIHAR", 25.69, 85.22), (800001, "PATNA CITY", "BIHAR", 25.6, 85.1))
    aliases = [DistrictAlias("Bihar", "PATNA CITY", "Patna", False, "test")]

    offices = office_districts(pincodes, nfhs, aliases).collect()

    assert sorted((o.pin, o.nfhs_district, o.approximate) for o in offices) == [("800001", "Patna", False), ("844101", "Vaishali", False)]


def test_checks_fail_on_a_repeated_cell(spark, nfhs):
    offices = spark.createDataFrame([("1", 25.7, 85.2, "Bihar", "Patna", False, "c1")], OFFICE_SCHEMA)
    built = build_district_cells(offices, nfhs)

    with pytest.raises(ValueError, match=r"h3_r5 is repeated: 2 rows for 1 cells"):
        check_district_cells(nfhs, built.unionByName(built))
