"""District link (#44), tested through `build_facility_districts` on small fake tables."""

import re

import pytest
from pyspark.sql import types as T

from talaria.district_link import build_facility_districts
from talaria.district_link.aliases import DistrictAlias, load_aliases
from talaria.district_link.checks import check_facility_districts
from talaria.district_link.link_counts import format_link_counts, link_counts
from talaria.silver_base.aliases import OFFICIAL_STATES

NFHS_DISTRICTS = [
    ("Kerala", "Kollam"),
    ("Kerala", "Kozhikode"),
    ("Karnataka", "Bangalore"),
    ("Karnataka", "Bangalore Rural"),
    ("Andhra Pradesh", "Visakhapatnam"),
    ("Haryana", "Gurgaon"),
    ("Bihar", "Aurangabad"),
    ("Maharashtra", "Aurangabad"),
]
ALIASES = [
    DistrictAlias("Karnataka", "BENGALURU URBAN", "Bangalore", False, "renamed"),
    DistrictAlias("Karnataka", "BENGALURU RURAL", "Bangalore Rural", False, "renamed"),
    DistrictAlias("Andhra Pradesh", "Anakapalli", "Visakhapatnam", True, "carved out"),
    DistrictAlias("Haryana", "GURUGRAM", "Gurgaon", False, "renamed"),
    DistrictAlias("West Bengal", "PURBA BARDHAMAN", None, False, "no NFHS-5 row"),
]
# Post offices: (pincode, district, statename, latitude, longitude), as the directory writes them.
OFFICES = [
    (691001, "KOLLAM", "KERALA", 8.88, 76.60),
    (560001, "BENGALURU URBAN", "KARNATAKA", 12.97, 77.59),
    (531001, "Anakapalli", "ANDHRA PRADESH", 17.69, 83.00),
    (824101, "AURANGABAD", "BIHAR", 24.75, 84.37),
    # 562157 spans two districts: two offices in Bengaluru Urban, one in Bengaluru Rural.
    (562157, "BENGALURU URBAN", "KARNATAKA", 13.10, 77.60),
    (562157, "BENGALURU URBAN", "KARNATAKA", 13.11, 77.61),
    (562157, "BENGALURU RURAL", "KARNATAKA", 13.30, 77.40),
    (713101, "PURBA BARDHAMAN", "WEST BENGAL", 23.23, 87.86),
]

FACILITY_SCHEMA = T.StructType(
    [T.StructField(name, T.StringType()) for name in ["unique_id", "address_pincode", "address_city", "address_state"]]
    + [T.StructField("latitude", T.DoubleType()), T.StructField("longitude", T.DoubleType())]
)


@pytest.fixture
def nfhs(spark):
    return spark.createDataFrame(NFHS_DISTRICTS, "state_ut string, district_name string")


@pytest.fixture
def link(spark, make_pincodes, nfhs):
    """`{unique_id: (nfhs_state, nfhs_district, district_link, district_approximate)}`, after the checks pass."""

    def run(*facilities, offices=OFFICES):
        df = spark.createDataFrame([_facility(i, f) for i, f in enumerate(facilities)], FACILITY_SCHEMA)
        districts = build_facility_districts(df, make_pincodes(*offices), nfhs, ALIASES)
        check_facility_districts(df, nfhs, districts, ALIASES)
        return {r.unique_id: (r.nfhs_state, r.nfhs_district, r.district_link, r.district_approximate) for r in districts.collect()}

    return run


def _facility(i, f):
    row = {"unique_id": f"f{i}", "address_pincode": None, "address_city": None, "address_state": None,
           "latitude": None, "longitude": None, **f}
    return tuple(row[name] for name in FACILITY_SCHEMA.fieldNames())


# (facility) -> (nfhs_state, nfhs_district, district_link, district_approximate).
CASES = {
    "PIN in one district, same name": (
        dict(address_pincode="691001"), ("Kerala", "Kollam", "pin", False)),
    "PIN district renamed since NFHS-5": (
        dict(address_pincode="560001"), ("Karnataka", "Bangalore", "pin", False)),
    "PIN district carved out since NFHS-5": (
        dict(address_pincode="531001"), ("Andhra Pradesh", "Visakhapatnam", "pin", True)),
    "PIN fixes the state of a repeated district name": (
        dict(address_pincode="824101", address_state="Maharashtra"), ("Bihar", "Aurangabad", "pin", False)),
    "PIN spans districts: nearest office": (
        dict(address_pincode="562157", latitude=13.29, longitude=77.41),
        ("Karnataka", "Bangalore Rural", "pin_nearest_office", False)),
    "PIN spans districts, no coordinates: most offices": (
        dict(address_pincode="562157"), ("Karnataka", "Bangalore", "pin_most_offices", True)),
    "PIN not in the directory: city": (
        dict(address_pincode="999999", address_city="Kozhikode", address_state="Kerala"),
        ("Kerala", "Kozhikode", "city", False)),
    "no PIN: city through an alias": (
        dict(address_city="Gurugram", address_state="Haryana"), ("Haryana", "Gurgaon", "city", False)),
    "city must be in the facility's state": (
        dict(address_city="Kozhikode", address_state="Karnataka"), (None, None, "unknown", False)),
    "PIN district without an NFHS-5 row, no city": (
        dict(address_pincode="713101"), (None, None, "unknown", False)),
    "nothing to go on": (dict(address_city="Nowhere", address_state="Kerala"), (None, None, "unknown", False)),
}


def test_links_each_facility_to_an_nfhs_district(link):
    rows = link(*[facility for facility, _ in CASES.values()])

    assert {case: rows[f"f{i}"] for i, case in enumerate(CASES)} == {case: expected for case, (_, expected) in CASES.items()}


def test_a_city_without_a_district_name_takes_its_facilities_majority(link):
    bengaluru = dict(address_city="Bengaluru", address_state="Karnataka")
    rows = link(
        *[bengaluru | dict(address_pincode="560001")] * 3,
        bengaluru,  # no PIN: its city's PIN-linked facilities are all in Bangalore
    )

    assert rows["f3"] == ("Karnataka", "Bangalore", "city_majority", True)


def test_no_city_majority_without_enough_agreement(link):
    bengaluru = dict(address_city="Bengaluru", address_state="Karnataka")
    rows = link(
        bengaluru | dict(address_pincode="560001"),
        bengaluru | dict(address_pincode="560001"),
        bengaluru | dict(address_pincode="562157", latitude=13.3, longitude=77.4),
        bengaluru,
    )

    assert rows["f3"] == (None, None, "unknown", False)


def test_link_counts(link, spark, make_pincodes, nfhs):
    df = spark.createDataFrame([_facility(0, dict(address_pincode="691001")), _facility(1, {})], FACILITY_SCHEMA)
    counts = link_counts(build_facility_districts(df, make_pincodes(*OFFICES), nfhs, ALIASES))

    assert counts["pin"] == {"facilities": 1, "approximate": 0}
    assert counts["unknown"] == {"facilities": 1, "approximate": 0}
    assert "pin_nearest_office" in format_link_counts(counts)


def test_checks_fail_on_an_alias_to_a_missing_district(spark, make_pincodes, nfhs):
    df = spark.createDataFrame([_facility(0, dict(address_pincode="691001"))], FACILITY_SCHEMA)
    wrong = [*ALIASES, DistrictAlias("Kerala", "QUILON", "Quilon", False, "typo")]
    districts = build_facility_districts(df, make_pincodes(*OFFICES), nfhs, wrong)

    with pytest.raises(ValueError, match=r"alias targets not in Silver NFHS-5: \['Kerala / Quilon'\]"):
        check_facility_districts(df, nfhs, districts, wrong)


def test_checks_fail_on_a_lost_facility(spark, make_pincodes, nfhs):
    df = spark.createDataFrame([_facility(0, {}), _facility(1, {})], FACILITY_SCHEMA)
    districts = build_facility_districts(df, make_pincodes(*OFFICES), nfhs, ALIASES).limit(1)

    with pytest.raises(ValueError, match=r"1 rows for 1 ids, facilities has 2"):
        check_facility_districts(df, nfhs, districts, ALIASES)


def test_the_alias_table_is_well_formed():
    aliases = load_aliases()
    keys = [(a.state, re.sub(r"[^a-z]", "", a.directory_district.lower())) for a in aliases]

    assert len(aliases) > 100
    assert len(set(keys)) == len(keys)
    for a in aliases:
        assert a.state in OFFICIAL_STATES, a
        assert a.note, a
        assert a.nfhs_district is not None or not a.approximate, a
