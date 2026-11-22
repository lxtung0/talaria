"""Silver base per-step counts (spec #1, "Runtime checks"), tested through `step_counts`.

Each test runs the real `build_silver_base` on a small fake bronze and checks
the counts against values worked out by hand from the fixture.
"""

import json

from talaria.silver_base import build_silver_base
from talaria.silver_base.step_counts import format_step_counts, step_counts


def _counts(bronze):
    return step_counts(bronze, build_silver_base(bronze))


def test_rows_removed_by_reason(make_bronze):
    duplicate = {"unique_id": "dup", "name": "City Hospital"}
    bronze = make_bronze(
        duplicate,
        duplicate,
        duplicate,
        {"unique_id": "fragment-1", "source_urls": None},
        {"unique_id": "fragment-2", "source_urls": None},
        {"unique_id": "kept"},
    )

    assert _counts(bronze)["rows"] == {
        "bronze": 6,
        "description_fragments_removed": 2,
        "exact_duplicates_removed": 2,
        "silver_base": 2,
    }


def test_values_set_to_null_by_type_of_missing_value(make_bronze):
    bronze = make_bronze(
        {
            "name": " NULL ",
            "address_city": " ",
            "description": "[]",
            "officialWebsite": "see [email protected]",
            "numberDoctors": "0",
            "specialties": '["", " "]',
            "organization_type": "null",  # dropped column: not counted
        },
        {"email": "[email protected]", "procedure": "null"},
    )

    assert _counts(bronze)["nulls"] == {
        "null_text": 2,
        "empty_text": 1,
        "empty_array_text": 1,
        "hidden_email": 2,
        "list_empty_after_cleanup": 1,
        "zero_doctors": 1,
    }


def test_items_removed_per_list_column(make_bronze):
    bronze = make_bronze(
        {
            "specialties": '["", "Cardiology", "cardiology", null]',
            "phone_numbers": '["9876543210", "+91 98765 43210"]',
            "email": "info@cityhospital.in",
            "procedure": "null",  # a Missing value, not an item
        },
        {"affiliationTypeIds": '["private", "Private-Entity"]', "equipment": "[]"},
    )

    assert _counts(bronze)["items_removed"] == {
        "specialties": 3,
        "procedure": 0,
        "equipment": 0,
        "capability": 0,
        "phone_numbers": 1,
        "websites": 0,
        "source_urls": 0,
        "affiliation_types": 1,
        "email": 0,
    }


def test_spelling_fixes_per_alias_table(make_bronze):
    bronze = make_bronze(
        {
            "facilityTypeId": "Farmacy",
            "operatorTypeId": "government",
            "address_stateOrRegion": "Tamilnadu",
            "address_city": "Bangalore",
            "affiliationTypeIds": '["private-entity", "Private-Entity", "ngo"]',
            "specialties": '["paediatricCardiology", "cardiology"]',
        },
        {"facilityTypeId": "Hospital", "address_stateOrRegion": "Gurugram, Haryana", "address_city": "pune"},
        {"operatorTypeId": "Private", "address_stateOrRegion": "Haryana"},
        {"address_stateOrRegion": "Thane"},
    )

    assert _counts(bronze)["spelling_fixes"] == {
        "facility_type": 1,
        "operator_type": 1,
        "affiliation_type": 2,
        "state": 2,
        "city": 1,
        "specialty": 1,
    }


def test_values_formatted_vs_left_unchanged(make_bronze):
    bronze = make_bronze(
        {
            "address_zipOrPostcode": "201 301",
            "officialPhone": "98765 43210",
            "phone_numbers": '["+919876543210", "12345"]',
            "email": "Info[at]City.in",
            "websites": '["https://www.city.in/", "Not Available Online"]',
            "officialWebsite": "city.in",
        },
        {"address_zipOrPostcode": "COCHIN-16"},
        {"address_zipOrPostcode": "110001"},
    )

    assert _counts(bronze)["formatting"] == {
        "address_pincode_formatted": 1,
        "address_pincode_unchanged": 2,
        "official_phone_formatted": 1,
        "official_phone_unchanged": 0,
        "phone_numbers_formatted": 0,
        "phone_numbers_unchanged": 2,
        "email_formatted": 1,
        "email_unchanged": 0,
        "official_website_formatted": 0,
        "official_website_unchanged": 1,
        "websites_formatted": 1,
        "websites_unchanged": 1,
        "facebook_link_formatted": 0,
        "facebook_link_unchanged": 0,
    }


def test_flags_set(make_bronze):
    fifty = json.dumps(["Cardiology"] * 50)
    bronze = make_bronze(
        {"specialties": fifty, "procedure": fifty},
        {"specialties": fifty, "capacity": "0"},
        {"capacity": "0"},
        {"capacity": "20"},
    )

    assert _counts(bronze)["flags"] == {
        "needs_investigation": 2,
        "truncated_specialties": 2,
        "truncated_procedure": 1,
        "truncated_equipment": 0,
        "truncated_capability": 0,
        "truncated_phone_numbers": 0,
        "truncated_websites": 0,
        "truncated_source_urls": 0,
        "truncated_affiliation_types": 0,
        "truncated_email": 0,
        "zero_beds": 2,
    }


def test_formatted_report_lists_every_count_by_section(make_bronze):
    report = format_step_counts(_counts(make_bronze({}, {})))

    assert report.splitlines()[:5] == [
        "rows",
        "  bronze: 2",
        "  description_fragments_removed: 0",
        "  exact_duplicates_removed: 0",
        "  silver_base: 2",
    ]
    for section in ["nulls", "items_removed", "spelling_fixes", "formatting", "flags"]:
        assert section in report.splitlines()
