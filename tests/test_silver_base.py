"""Silver base behaviour, tested only through `build_silver_base` (spec #1, Testing Decisions)."""

import pytest

from talaria.silver_base import build_silver_base


def test_description_fragments_are_removed(make_bronze):
    bronze = make_bronze(
        {"unique_id": "real", "name": "City Hospital"},
        {"unique_id": "fragment", "name": "and a 24x7 pharmacy.", "source_urls": None},
    )

    silver = build_silver_base(bronze)

    assert [row.unique_id for row in silver.collect()] == ["real"]


def test_exact_duplicates_are_collapsed_to_one_row(make_bronze):
    facility = {"unique_id": "dup", "name": "City Hospital", "address_city": "Pune"}
    bronze = make_bronze(facility, facility, {"unique_id": "other"})

    silver = build_silver_base(bronze)

    assert sorted(row.unique_id for row in silver.collect()) == ["dup", "other"]


DROPPED_COLUMNS = {
    "acceptsVolunteers", "address_country", "address_countryCode", "countries",
    "custom_logo_presence", "engagement_metrics_n_engagements",
    "engagement_metrics_n_followers", "engagement_metrics_n_likes",
    "organization_type", "post_metrics_most_recent_social_media_post_date",
    "post_metrics_post_count", "source", "coordinates", "content_table_id",
    "source_types", "source_ids",
}


def test_drops_the_sixteen_unused_columns(make_bronze):
    silver = build_silver_base(make_bronze({}))

    assert len(DROPPED_COLUMNS) == 16
    assert DROPPED_COLUMNS.isdisjoint(silver.columns)


def test_keeps_the_bronze_ingest_columns(make_bronze):
    silver = build_silver_base(make_bronze({}))

    assert {"_source_table", "_ingested_at"} <= set(silver.columns)


def test_output_columns_follow_the_rename_table(make_bronze):
    silver = build_silver_base(make_bronze({}))

    assert silver.columns == [
        "unique_id", "source_content_id", "name", "phone_numbers",
        "official_phone", "email", "websites", "official_website",
        "year_established", "facebook_link", "address_line1", "address_line2",
        "address_line3", "address_city", "address_state", "address_pincode",
        "facility_type", "operator_type", "affiliation_types", "description",
        "area", "number_doctors", "bed_count", "specialties", "procedure",
        "equipment", "capability", "recency_of_page_update",
        "distinct_social_media_presence_count", "affiliated_staff_presence",
        "number_of_facts_about_the_organization", "latitude", "longitude",
        "cluster_id", "source_urls", "_source_table", "_ingested_at",
        "needs_investigation", "truncated_columns",
    ]


def test_renamed_columns_keep_their_values(make_bronze):
    bronze = make_bronze({"capacity": "120", "address_stateOrRegion": "Kerala"})

    row = build_silver_base(bronze).first()

    assert (row.bed_count, row.address_state) == ("120", "Kerala")


def test_raises_when_unique_id_repeats_after_cleanup(make_bronze):
    bronze = make_bronze(
        {"unique_id": "same", "name": "City Hospital"},
        {"unique_id": "same", "name": "City Hospital Annex"},
    )

    with pytest.raises(ValueError, match="unique_id"):
        build_silver_base(bronze)


def test_raises_when_unique_id_is_null_after_cleanup(make_bronze):
    bronze = make_bronze({"unique_id": None, "name": "Nameless Clinic"})

    with pytest.raises(ValueError, match="unique_id"):
        build_silver_base(bronze)


def test_whitespace_of_every_kind_is_trimmed_from_both_ends(make_bronze):
    bronze = make_bronze(
        {"address_city": " ​ Pune\t\n﻿"},
        {"address_city": "\u2007\u202fKochi\u00a0"},
    )

    cities = [row.address_city for row in build_silver_base(bronze).orderBy("unique_id").collect()]

    assert cities == ["Pune", "Kochi"]


def test_inner_runs_of_whitespace_collapse_to_one_space(make_bronze):
    bronze = make_bronze({"address_line1": "12  MG\u00a0\u00a0Road,\t\nNear\u200bBus  Stand"})

    row = build_silver_base(bronze).first()

    assert row.address_line1 == "12 MG Road, Near Bus Stand"


def test_name_and_description_get_whitespace_normalization_only(make_bronze):
    bronze = make_bronze(
        {"name": "  AIIMS   **Rishikesh**\u00a0", "description": "Est. 2012 [1]:\n\n  *24x7* ICU  "}
    )

    row = build_silver_base(bronze).first()

    assert (row.name, row.description) == ("AIIMS **Rishikesh**", "Est. 2012 [1]: *24x7* ICU")


@pytest.mark.parametrize("missing", ["null", "NULL", "Null", "", "[]", "  null\u00a0", "\u200b"])
def test_missing_value_spellings_become_null(make_bronze, missing):
    bronze = make_bronze({"address_city": missing, "officialPhone": missing, "description": missing})

    row = build_silver_base(bronze).first()

    assert (row.address_city, row.official_phone, row.description) == (None, None, None)


def test_a_value_containing_the_hidden_email_placeholder_becomes_null(make_bronze):
    bronze = make_bronze({"officialWebsite": "[email\u00a0protected]"}, {"officialWebsite": "Contact: [email protected]"})

    websites = [row.official_website for row in build_silver_base(bronze).collect()]

    assert websites == [None, None]


def test_real_values_resembling_missing_spellings_are_kept(make_bronze):
    bronze = make_bronze({"name": "Nullah Bazar Clinic", "address_line2": "[1] Main Road"})

    row = build_silver_base(bronze).first()

    assert (row.name, row.address_line2) == ("Nullah Bazar Clinic", "[1] Main Road")


def test_an_empty_list_column_becomes_null(make_bronze):
    bronze = make_bronze({"specialties": " [] ", "phone_numbers": "NULL"})

    row = build_silver_base(bronze).first()

    assert (row.specialties, row.phone_numbers) == (None, None)


def test_a_list_with_a_placeholder_item_keeps_its_other_items(make_bronze):
    bronze = make_bronze({"email": '["[email protected]", "info@cityhospital.in"]'})

    row = build_silver_base(bronze).first()

    assert row.email is not None
    assert "info@cityhospital.in" in str(row.email)


LIST_COLUMNS = [
    "specialties", "procedure", "equipment", "capability", "phone_numbers",
    "websites", "source_urls", "affiliation_types", "email",
]


def test_list_columns_are_arrays_of_strings(make_bronze):
    silver = build_silver_base(make_bronze({}))

    types = {f.name: f.dataType.simpleString() for f in silver.schema.fields}
    assert {name: types[name] for name in LIST_COLUMNS} == {name: "array<string>" for name in LIST_COLUMNS}


def test_a_json_list_becomes_its_items_in_order(make_bronze):
    bronze = make_bronze({"specialties": '["cardiology", "nephrology", "neurology"]'})

    row = build_silver_base(bronze).first()

    assert row.specialties == ["cardiology", "nephrology", "neurology"]


def test_a_single_email_becomes_a_one_item_list(make_bronze):
    bronze = make_bronze({"email": " info@cityhospital.in "})

    row = build_silver_base(bronze).first()

    assert row.email == ["info@cityhospital.in"]


def test_an_email_list_keeps_every_address(make_bronze):
    bronze = make_bronze({"email": '["info@cityhospital.in", "opd@cityhospital.in"]'})

    row = build_silver_base(bronze).first()

    assert row.email == ["info@cityhospital.in", "opd@cityhospital.in"]


def test_list_items_are_whitespace_normalized(make_bronze):
    bronze = make_bronze({"procedure": '["  knee\\u00a0 replacement\\n", "\\u200bdialysis"]'})

    row = build_silver_base(bronze).first()

    assert row.procedure == ["knee replacement", "dialysis"]


def test_empty_null_and_missing_items_are_dropped(make_bronze):
    bronze = make_bronze(
        {"equipment": '["", "MRI", null, "  ", "NULL", "[]", "CT scanner"]'},
        {"email": '["[email\\u00a0protected]", "info@cityhospital.in"]'},
    )

    rows = build_silver_base(bronze).orderBy("unique_id").collect()

    assert (rows[0].equipment, rows[1].email) == (["MRI", "CT scanner"], ["info@cityhospital.in"])


def test_a_list_left_empty_after_cleanup_becomes_null(make_bronze):
    bronze = make_bronze({"capability": '["", null, " null "]', "email": '["[email protected]"]'})

    row = build_silver_base(bronze).first()

    assert (row.capability, row.email) == (None, None)


def test_duplicate_items_collapse_to_the_first_spelling_in_order(make_bronze):
    bronze = make_bronze(
        {
            "procedure": (
                '["Laparoscopic Surgery", "Dialysis", "laparoscopic surgery", '
                '"Laparoscopic-Surgery", "dialysis.", "Cataract Surgery", "cataract surgerys"]'
            ),
            "equipment": '["MRI Scanner", "MRI scanners", "X-ray", "xray"]',
            "affiliationTypeIds": '["private-entity", "Private Entity", "NAAC"]',
        }
    )

    row = build_silver_base(bronze).first()

    assert row.procedure == ["Laparoscopic Surgery", "Dialysis", "Cataract Surgery"]
    assert row.equipment == ["MRI Scanner", "X-ray"]
    assert row.affiliation_types == ["private-entity", "NAAC"]


def test_items_differing_by_real_letters_stay_separate(make_bronze):
    bronze = make_bronze(
        {
            "specialties": '["nephrology", "neurology"]',
            "procedure": '["IUI treatment", "IVF treatment", "type 1 diabetes", "type 2 diabetes"]',
        }
    )

    row = build_silver_base(bronze).first()

    assert row.specialties == ["nephrology", "neurology"]
    assert row.procedure == ["IUI treatment", "IVF treatment", "type 1 diabetes", "type 2 diabetes"]


def test_identifier_lists_dedupe_on_exact_equality_only(make_bronze):
    bronze = make_bronze(
        {
            "websites": '["cityhospital.in/About", "cityhospital.in/about", "cityhospital.in/About"]',
            "email": '["info@cityhospital.in", "Info@cityhospital.in", "info@cityhospital.in"]',
            "phone_numbers": '["+919876543210", "+91 98765 43210", "+919876543210"]',
        }
    )

    row = build_silver_base(bronze).first()

    assert row.websites == ["cityhospital.in/About", "cityhospital.in/about"]
    assert row.email == ["info@cityhospital.in", "Info@cityhospital.in"]
    assert row.phone_numbers == ["+919876543210", "+91 98765 43210"]


def test_source_urls_are_kept_as_captured_apart_from_exact_duplicates(make_bronze):
    bronze = make_bronze(
        {
            "source_urls": (
                '["https://www.CityHospital.in/About/", "https://cityhospital.in/about", '
                '"https://www.CityHospital.in/About/"]'
            )
        }
    )

    row = build_silver_base(bronze).first()

    assert row.source_urls == ["https://www.CityHospital.in/About/", "https://cityhospital.in/about"]


def _json_list(items):
    return "[" + ", ".join("null" if item is None else f'"{item}"' for item in items) + "]"


def test_a_list_at_the_50_item_cap_marks_the_facility_for_investigation(make_bronze):
    bronze = make_bronze(
        {
            "capability": _json_list(f"service {n}" for n in range(50)),
            "affiliationTypeIds": _json_list(["private"] * 50),
        }
    )

    row = build_silver_base(bronze).first()

    assert row.needs_investigation is True
    assert row.truncated_columns == ["capability", "affiliation_types"]


def test_a_heavily_duplicated_50_item_list_is_still_truncated(make_bronze):
    items = ["Dialysis", "dialysis", "", None, "DIALYSIS."] * 10
    bronze = make_bronze({"procedure": _json_list(items)})

    row = build_silver_base(bronze).first()

    assert row.procedure == ["Dialysis"]
    assert (row.needs_investigation, row.truncated_columns) == (True, ["procedure"])


def test_lists_below_the_cap_are_not_truncated(make_bronze):
    bronze = make_bronze(
        {"specialties": _json_list(f"specialty {n}" for n in range(49)), "email": "info@cityhospital.in"},
        {},
    )

    rows = build_silver_base(bronze).collect()

    assert [(row.needs_investigation, row.truncated_columns) for row in rows] == [(False, None), (False, None)]


def test_flag_columns_have_their_types(make_bronze):
    silver = build_silver_base(make_bronze({}))

    types = {f.name: f.dataType.simpleString() for f in silver.schema.fields}
    assert (types["needs_investigation"], types["truncated_columns"]) == ("boolean", "array<string>")
