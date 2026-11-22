"""Group H, location flags (spec #13, #19), tested only through `build_silver_facilities`.

Only Facilities with a Silver base location flag are checked. These tests make
one with `flag_pin_mismatch`: the written state (Kerala) and the city (Kochi,
a Kerala district) agree against the PIN (500001, Hyderabad, Telangana).
"""

import datetime

import pytest

from talaria.silver_facilities import build_silver_facilities
from talaria.silver_facilities.checks import check_silver_facilities

RUN_DATE = datetime.date(2026, 11, 21)
H_FLAGS = ["flag_coords_far_from_written_pin", "flag_no_same_prefix_pin_nearby", "flag_coords_shared"]

HYDERABAD = (17.3850, 78.4867)  # PIN 500001
SECUNDERABAD = (17.4399, 78.4983)  # PIN 500003, same 500 prefix, about 6 km from 500001
SHAMSHABAD = (17.2403, 78.4294)  # PIN 501218, about 17 km from 500001, different prefix
GACHIBOWLI = (17.4401, 78.3489)  # PIN 500032, about 16 km from 500001, same prefix
KOCHI = (9.9312, 76.2673)  # PIN 682001


@pytest.fixture(scope="module")
def directory(make_pincodes):
    return make_pincodes(
        (500001, "HYDERABAD", "TELANGANA", *HYDERABAD),
        (500003, "HYDERABAD", "TELANGANA", *SECUNDERABAD),
        (500032, "HYDERABAD", "TELANGANA", *GACHIBOWLI),
        (501218, "RANGAREDDY", "TELANGANA", *SHAMSHABAD),
        (682001, "KOCHI", "KERALA", *KOCHI),
        # A directory office with unusable coordinates is skipped, never an error.
        (682001, "KOCHI", "KERALA", "NA", "NA"),
    )


def pin_mismatch(unique_id, coordinates, pin="500001"):
    """A Facility Silver base flags with `flag_pin_mismatch`, at `coordinates`."""
    latitude, longitude = coordinates if coordinates else (None, None)
    return {
        "unique_id": unique_id,
        "address_stateOrRegion": "Kerala",
        "address_city": "Kochi",
        "address_zipOrPostcode": pin,
        "latitude": latitude,
        "longitude": longitude,
    }


def unflagged(unique_id, coordinates):
    """A Facility whose state, city and PIN agree (Telangana, Hyderabad, 500001)."""
    latitude, longitude = coordinates
    return {
        "unique_id": unique_id,
        "address_stateOrRegion": "Telangana",
        "address_city": "Hyderabad",
        "address_zipOrPostcode": "500001",
        "latitude": latitude,
        "longitude": longitude,
    }


@pytest.fixture
def run(make_silver_inputs, directory):
    """Group H flags by `unique_id`, plus the inputs and output for further checks."""

    def build(*rows):
        bronze, silver_base = make_silver_inputs(*rows, pincodes=directory)
        facilities = build_silver_facilities(silver_base, bronze, directory, RUN_DATE)
        flags = {row.unique_id: tuple(row[name] for name in H_FLAGS) for row in facilities.collect()}
        return flags, silver_base, facilities

    return build


def test_setup_gives_the_silver_base_location_flags(run):
    _, silver_base, _ = run(pin_mismatch("flagged", HYDERABAD), unflagged("clean", HYDERABAD))

    rows = {row.unique_id: row for row in silver_base.collect()}
    assert rows["flagged"].flag_pin_mismatch is True
    assert not any(rows["clean"][name] for name in ["flag_state_corrected", "flag_pin_mismatch", "flag_address_conflict", "flag_pin_unverified"])


def test_near_its_pin_gives_no_location_flag(run):
    flags, _, _ = run(pin_mismatch("near", HYDERABAD))

    assert flags["near"] == (False, False, False)


def test_far_from_its_pin_with_a_same_prefix_pin_nearby(run):
    flags, _, _ = run(pin_mismatch("gachibowli", GACHIBOWLI))

    far, no_same_prefix, shared = flags["gachibowli"]
    assert (far, no_same_prefix, shared) == (True, False, False)


def test_far_with_no_same_prefix_pin_nearby(run):
    flags, _, _ = run(pin_mismatch("shamshabad", SHAMSHABAD), pin_mismatch("kochi", KOCHI))

    assert flags["shamshabad"] == (True, True, False)
    assert flags["kochi"] == (True, True, False)


def test_far_uses_the_pin_radius_when_it_exceeds_10_km(run, make_silver_inputs, make_pincodes):
    # A PIN whose offices sit about 33 km either side of its centroid: its radius,
    # not the 10 km floor, decides what counts as far.
    wide = make_pincodes(
        (500001, "HYDERABAD", "TELANGANA", *HYDERABAD),
        (500001, "HYDERABAD", "TELANGANA", 17.6850, 78.4867),  # about 33 km north
        (500001, "HYDERABAD", "TELANGANA", 17.0850, 78.4867),  # about 33 km south
        (682001, "KOCHI", "KERALA", *KOCHI),
    )
    bronze, silver_base = make_silver_inputs(pin_mismatch("wide", GACHIBOWLI), pincodes=wide)

    facilities = build_silver_facilities(silver_base, bronze, wide, RUN_DATE)

    # About 16 km from the centroid, inside the PIN's 33 km radius.
    assert facilities.first().flag_coords_far_from_written_pin is False


def test_shared_coordinates(run):
    flags, _, _ = run(pin_mismatch("flagged", HYDERABAD), unflagged("neighbour", HYDERABAD))

    assert flags["flagged"][2] is True
    # The unflagged Facility shares them too, but is out of scope.
    assert flags["neighbour"] == (False, False, False)


def test_unflagged_facility_is_never_checked(run):
    flags, _, _ = run(unflagged("far-away", KOCHI), unflagged("twin", KOCHI))

    assert flags["far-away"] == (False, False, False)
    assert flags["twin"] == (False, False, False)


def test_flagged_without_coordinates_gives_no_location_flag(run):
    flags, _, _ = run(pin_mismatch("no-coordinates", None))

    assert flags["no-coordinates"] == (False, False, False)


def test_pin_not_in_directory_is_not_far_but_can_lack_a_same_prefix_pin(run):
    # 500099 isn't in the directory, so Silver base flags it `flag_pin_unverified`.
    near = {**unflagged("unverified-near", HYDERABAD), "address_zipOrPostcode": "500099"}
    lonely = {**unflagged("unverified-far", KOCHI), "address_zipOrPostcode": "500099"}

    flags, silver_base, _ = run(near, lonely)

    assert {row.unique_id: row.flag_pin_unverified for row in silver_base.collect()} == {
        "unverified-near": True,
        "unverified-far": True,
    }
    assert flags["unverified-near"] == (False, False, False)
    assert flags["unverified-far"] == (False, True, False)


def test_no_working_column_is_stored(run):
    _, silver_base, facilities = run(pin_mismatch("flagged", GACHIBOWLI))

    added = facilities.columns[len(silver_base.columns) :]
    assert not [name for name in added if not name.startswith("flag_")]
    assert set(H_FLAGS) <= set(added)


def test_location_flags_are_never_null(run):
    _, _, facilities = run(pin_mismatch("a", HYDERABAD), unflagged("b", KOCHI), pin_mismatch("c", None))

    for name in H_FLAGS:
        assert facilities.where(facilities[name].isNull()).count() == 0


def test_runtime_check_passes_on_real_output(run):
    _, silver_base, facilities = run(pin_mismatch("a", GACHIBOWLI), unflagged("b", KOCHI))

    check_silver_facilities(silver_base, facilities)


def test_runtime_check_fails_when_an_unflagged_facility_has_a_location_flag(run):
    from pyspark.sql import functions as F

    _, silver_base, facilities = run(pin_mismatch("a", GACHIBOWLI), unflagged("b", KOCHI))
    broken = facilities.withColumn(
        "flag_coords_shared", F.when(F.col("unique_id") == "b", True).otherwise(F.col("flag_coords_shared"))
    )

    with pytest.raises(ValueError, match="flag_coords_shared.*without a Silver base location flag"):
        check_silver_facilities(silver_base, broken)
