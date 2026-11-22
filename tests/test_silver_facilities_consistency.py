"""Groups C and D, specialty and description consistency (spec #13, #17), tested only
through `build_silver_facilities`."""

import datetime
import json

import pytest

from talaria.silver_facilities import build_silver_facilities
from talaria.silver_facilities.checks import check_silver_facilities
from talaria.silver_facilities.specialty_synonyms import SPECIALTY_GROUPS

RUN_DATE = datetime.date(2026, 11, 21)


@pytest.fixture
def build(make_silver_inputs, no_pincodes):
    """Silver facilities rows by `unique_id`, from partial bronze rows, after the runtime checks pass."""

    def run(*rows):
        bronze, silver_base = make_silver_inputs(*rows)
        facilities = build_silver_facilities(silver_base, bronze, no_pincodes, RUN_DATE)
        check_silver_facilities(silver_base, facilities)
        return {row.unique_id: row for row in facilities.collect()}

    return run


# C. (specialties, capability sentences) -> flag_specialty_unsupported_by_capability.
SPECIALTY = {
    "named directly": (["internalMedicine"], ["Offers internal medicine consultations"], False),
    "code split into words": (["gynecologyAndObstetrics"], ["Department of gynecology and obstetrics"], False),
    "synonym of its group": (["dentistry"], ["Offers dental care for all ages"], False),
    "synonym as a word start": (["ophthalmology"], ["An ophthalmologist is on staff"], False),
    "one of several specialties backed": (["cardiology", "urology"], ["Urology clinic"], False),
    "any sentence counts": (["nephrology"], ["Open all week", "Dialysis unit with 10 beds"], False),
    "case-insensitive": (["ent"], ["ENT clinic"], False),
    "British capability spelling": (["pediatrics"], ["Paediatric ward"], False),
    "not backed": (["cardiology"], ["Open 24 hours", "Ample parking"], True),
    "generic word is no synonym": (["cardiology"], ["Heart care available"], True),
    "short synonym is a whole word": (["ent"], ["Entire team on call"], True),
    "synonym must start a word": (["urology"], ["Neurology ward"], True),
    "another group's synonym": (["dentistry"], ["Eye care clinic", "Ophthalmology services"], True),
}


def test_specialty_unsupported_by_capability(build):
    rows = build(
        *[
            {"unique_id": case, "specialties": json.dumps(specialties), "capability": json.dumps(capability)}
            for case, (specialties, capability, _) in SPECIALTY.items()
        ]
    )

    assert {case: rows[case].flag_specialty_unsupported_by_capability for case in SPECIALTY} == {
        case: expected for case, (*_, expected) in SPECIALTY.items()
    }


@pytest.mark.parametrize(
    "row, truncated",
    [
        ({"specialties": None, "capability": '["Open 24 hours"]'}, None),
        ({"specialties": '["cardiology"]', "capability": None}, None),
        ({"specialties": json.dumps([f"specialty{i}" for i in range(50)]), "capability": '["Open"]'}, "specialties"),
        ({"specialties": '["cardiology"]', "capability": json.dumps([f"Fact {i}" for i in range(50)])}, "capability"),
    ],
)
def test_specialty_flag_is_false_when_it_cant_check(build, row, truncated):
    facility = build(row)["facility-1"]

    assert facility.truncated_columns == ([truncated] if truncated else None)
    assert facility.flag_specialty_unsupported_by_capability is False


def test_synonyms_are_reviewable_data():
    """Every group names its specialties and synonyms as plain lower-case terms."""
    assert SPECIALTY_GROUPS
    for group in SPECIALTY_GROUPS:
        assert group.specialties and group.synonyms, group.name
        for term in group.specialties + group.synonyms:
            assert term == term.lower().strip() and term.rstrip("*"), (group.name, term)


# D. (address_state as written, description) -> flag_desc_mentions_other_state.
DESCRIPTION = {
    "other state": ("Kerala", "Part of a hospital group based in Tamil Nadu.", True),
    "own state only": ("Kerala", "A leading hospital in Kochi, Kerala.", False),
    "own and another state": ("Kerala", "Serving Kerala and Karnataka.", True),
    "case-insensitive": ("Kerala", "BRANCH OF A TAMIL NADU CHAIN", True),
    "ampersand for and": ("Punjab", "Patients come from Jammu & Kashmir.", True),
    "longer name containing a state": ("Haryana", "Close to New Delhi.", True),
    "whole words only": ("Kerala", "Serves Goan and Bihari food in the canteen.", False),
    "state fixed by Silver base": ("Tamilnadu", "The best clinic in Tamil Nadu.", False),
    "non-official state": ("Kochi", "Part of a hospital group based in Tamil Nadu.", False),
    "no state": (None, "Part of a hospital group based in Tamil Nadu.", False),
    "no description": ("Kerala", None, False),
}


def test_description_mentions_other_state(build):
    rows = build(
        *[
            {"unique_id": case, "address_stateOrRegion": state, "description": description}
            for case, (state, description, _) in DESCRIPTION.items()
        ]
    )

    assert {case: rows[case].flag_desc_mentions_other_state for case in DESCRIPTION} == {
        case: expected for case, (*_, expected) in DESCRIPTION.items()
    }
