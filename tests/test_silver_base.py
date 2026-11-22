"""Silver base behaviour, tested only through `build_silver_base` (spec #1, Testing Decisions)."""

import pytest

from talaria.silver_base import build_silver_base


def test_description_fragments_are_removed(make_bronze, no_pincodes):
    bronze = make_bronze(
        {"unique_id": "real", "name": "City Hospital"},
        {"unique_id": "fragment", "name": "and a 24x7 pharmacy.", "source_urls": None},
    )

    silver = build_silver_base(bronze, no_pincodes)

    assert [row.unique_id for row in silver.collect()] == ["real"]


def test_exact_duplicates_are_collapsed_to_one_row(make_bronze, no_pincodes):
    facility = {"unique_id": "dup", "name": "City Hospital", "address_city": "Pune"}
    bronze = make_bronze(facility, facility, {"unique_id": "other"})

    silver = build_silver_base(bronze, no_pincodes)

    assert sorted(row.unique_id for row in silver.collect()) == ["dup", "other"]


DROPPED_COLUMNS = {
    "acceptsVolunteers", "address_country", "address_countryCode", "countries",
    "custom_logo_presence", "engagement_metrics_n_engagements",
    "engagement_metrics_n_followers", "engagement_metrics_n_likes",
    "organization_type", "post_metrics_most_recent_social_media_post_date",
    "post_metrics_post_count", "source", "coordinates", "content_table_id",
    "source_types", "source_ids",
}


def test_drops_the_sixteen_unused_columns(make_bronze, no_pincodes):
    silver = build_silver_base(make_bronze({}), no_pincodes)

    assert len(DROPPED_COLUMNS) == 16
    assert DROPPED_COLUMNS.isdisjoint(silver.columns)


def test_keeps_the_bronze_ingest_columns(make_bronze, no_pincodes):
    silver = build_silver_base(make_bronze({}), no_pincodes)

    assert {"_source_table", "_ingested_at"} <= set(silver.columns)


def test_output_columns_follow_the_rename_table(make_bronze, no_pincodes):
    silver = build_silver_base(make_bronze({}), no_pincodes)

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
        "needs_investigation", "truncated_columns", "flag_zero_beds",
        "flag_state_corrected", "flag_pin_mismatch", "flag_address_conflict", "flag_pin_unverified",
    ]


def test_renamed_columns_keep_their_values(make_bronze, no_pincodes):
    bronze = make_bronze({"capacity": "120", "address_stateOrRegion": "Kerala"})

    row = build_silver_base(bronze, no_pincodes).first()

    assert (row.bed_count, row.address_state) == (120, "Kerala")


def test_raises_when_unique_id_repeats_after_cleanup(make_bronze, no_pincodes):
    bronze = make_bronze(
        {"unique_id": "same", "name": "City Hospital"},
        {"unique_id": "same", "name": "City Hospital Annex"},
    )

    with pytest.raises(ValueError, match="unique_id"):
        build_silver_base(bronze, no_pincodes)


def test_raises_when_unique_id_is_null_after_cleanup(make_bronze, no_pincodes):
    bronze = make_bronze({"unique_id": None, "name": "Nameless Clinic"})

    with pytest.raises(ValueError, match="unique_id"):
        build_silver_base(bronze, no_pincodes)


def test_whitespace_of_every_kind_is_trimmed_from_both_ends(make_bronze, no_pincodes):
    bronze = make_bronze(
        {"address_city": " ​ Pune\t\n﻿"},
        {"address_city": "\u2007\u202fKochi\u00a0"},
    )

    cities = [row.address_city for row in build_silver_base(bronze, no_pincodes).orderBy("unique_id").collect()]

    assert cities == ["Pune", "Kochi"]


def test_inner_runs_of_whitespace_collapse_to_one_space(make_bronze, no_pincodes):
    bronze = make_bronze({"address_line1": "12  MG\u00a0\u00a0Road,\t\nNear\u200bBus  Stand"})

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.address_line1 == "12 MG Road, Near Bus Stand"


def test_name_and_description_get_whitespace_normalization_only(make_bronze, no_pincodes):
    bronze = make_bronze(
        {"name": "  AIIMS   **Rishikesh**\u00a0", "description": "Est. 2012 [1]:\n\n  *24x7* ICU  "}
    )

    row = build_silver_base(bronze, no_pincodes).first()

    assert (row.name, row.description) == ("AIIMS **Rishikesh**", "Est. 2012 [1]: *24x7* ICU")


@pytest.mark.parametrize("missing", ["null", "NULL", "Null", "", "[]", "  null\u00a0", "\u200b"])
def test_missing_value_spellings_become_null(make_bronze, no_pincodes, missing):
    bronze = make_bronze({"address_city": missing, "officialPhone": missing, "description": missing})

    row = build_silver_base(bronze, no_pincodes).first()

    assert (row.address_city, row.official_phone, row.description) == (None, None, None)


def test_a_value_containing_the_hidden_email_placeholder_becomes_null(make_bronze, no_pincodes):
    bronze = make_bronze({"officialWebsite": "[email\u00a0protected]"}, {"officialWebsite": "Contact: [email protected]"})

    websites = [row.official_website for row in build_silver_base(bronze, no_pincodes).collect()]

    assert websites == [None, None]


def test_real_values_resembling_missing_spellings_are_kept(make_bronze, no_pincodes):
    bronze = make_bronze({"name": "Nullah Bazar Clinic", "address_line2": "[1] Main Road"})

    row = build_silver_base(bronze, no_pincodes).first()

    assert (row.name, row.address_line2) == ("Nullah Bazar Clinic", "[1] Main Road")


def test_an_empty_list_column_becomes_null(make_bronze, no_pincodes):
    bronze = make_bronze({"specialties": " [] ", "phone_numbers": "NULL"})

    row = build_silver_base(bronze, no_pincodes).first()

    assert (row.specialties, row.phone_numbers) == (None, None)


def test_a_list_with_a_placeholder_item_keeps_its_other_items(make_bronze, no_pincodes):
    bronze = make_bronze({"email": '["[email protected]", "info@cityhospital.in"]'})

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.email is not None
    assert "info@cityhospital.in" in str(row.email)


def test_zero_doctors_becomes_null_and_the_facility_is_kept(make_bronze, no_pincodes):
    bronze = make_bronze({"unique_id": "zero", "numberDoctors": "0"}, {"unique_id": "some", "numberDoctors": "12"})

    rows = build_silver_base(bronze, no_pincodes).orderBy("unique_id").collect()

    assert [(row.unique_id, row.number_doctors) for row in rows] == [("some", 12), ("zero", None)]


def test_zero_beds_are_kept_and_flagged(make_bronze, no_pincodes):
    bronze = make_bronze(
        {"unique_id": "a-zero", "capacity": "0"},
        {"unique_id": "b-some", "capacity": "40"},
        {"unique_id": "c-unknown", "capacity": None},
    )

    rows = build_silver_base(bronze, no_pincodes).orderBy("unique_id").collect()

    assert [(row.bed_count, row.flag_zero_beds) for row in rows] == [(0, True), (40, False), (None, False)]


def test_address_line3_repeating_line2_after_whitespace_normalization_becomes_null(make_bronze, no_pincodes):
    bronze = make_bronze(
        {"unique_id": "a-repeat", "address_line2": "Near Bus Stand", "address_line3": " Near  Bus Stand "},
        {"unique_id": "b-distinct", "address_line2": "Near Bus Stand", "address_line3": "Kothrud"},
    )

    rows = build_silver_base(bronze, no_pincodes).orderBy("unique_id").collect()

    assert [(row.address_line2, row.address_line3) for row in rows] == [
        ("Near Bus Stand", None),
        ("Near Bus Stand", "Kothrud"),
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("October 2025", "2025-10-01"),
        ("January 2019", "2019-01-01"),
        ("3 weeks ago", "3 weeks ago"),
        ("2 months ago", "2 months ago"),
    ],
)
def test_month_year_page_updates_become_iso_dates_and_others_are_unchanged(make_bronze, no_pincodes, raw, expected):
    silver = build_silver_base(make_bronze({"recency_of_page_update": raw}), no_pincodes)

    assert silver.first().recency_of_page_update == expected
    assert silver.schema["recency_of_page_update"].dataType.simpleString() == "string"


def test_numeric_and_boolean_columns_are_converted_and_text_columns_stay_text(make_bronze, no_pincodes):
    bronze = make_bronze(
        {
            "yearEstablished": "1998",
            "numberDoctors": "25",
            "capacity": "120",
            "distinct_social_media_presence_count": "3",
            "number_of_facts_about_the_organization": "7",
            "area": "1500.5",
            "affiliated_staff_presence": "true",
            "recency_of_page_update": "October 2025",
            "address_zipOrPostcode": "411038",
            "officialPhone": "+919876543210",
            "latitude": 18.52,
            "longitude": 73.85,
        }
    )

    silver = build_silver_base(bronze, no_pincodes)

    types = {f.name: f.dataType.simpleString() for f in silver.schema.fields}
    assert {name: types[name] for name in [
        "year_established", "number_doctors", "bed_count",
        "distinct_social_media_presence_count", "number_of_facts_about_the_organization",
        "area", "affiliated_staff_presence", "flag_zero_beds", "latitude", "longitude",
        "recency_of_page_update", "address_pincode", "official_phone",
    ]} == {
        "year_established": "int", "number_doctors": "int", "bed_count": "int",
        "distinct_social_media_presence_count": "int", "number_of_facts_about_the_organization": "int",
        "area": "double", "affiliated_staff_presence": "boolean", "flag_zero_beds": "boolean",
        "latitude": "double", "longitude": "double",
        "recency_of_page_update": "string", "address_pincode": "string", "official_phone": "string",
    }
    row = silver.first()
    assert (row.year_established, row.number_doctors, row.bed_count, row.area, row.affiliated_staff_presence) == (
        1998, 25, 120, 1500.5, True,
    )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("yearEstablished", "around 1998"),
        ("numberDoctors", "twenty"),
        ("capacity", "120 beds"),
        ("area", "1500 sq ft"),
        ("affiliated_staff_presence", "maybe"),
    ],
)
def test_a_value_that_fails_to_convert_raises(make_bronze, no_pincodes, column, value):
    bronze = make_bronze({column: value})

    with pytest.raises(ValueError, match=column):
        build_silver_base(bronze, no_pincodes)


def test_missing_values_in_typed_columns_become_null_without_raising(make_bronze, no_pincodes):
    bronze = make_bronze({"yearEstablished": "null", "area": "", "affiliated_staff_presence": None})

    row = build_silver_base(bronze, no_pincodes).first()

    assert (row.year_established, row.area, row.affiliated_staff_presence) == (None, None, None)


LIST_COLUMNS = [
    "specialties", "procedure", "equipment", "capability", "phone_numbers",
    "websites", "source_urls", "affiliation_types", "email",
]


def test_list_columns_are_arrays_of_strings(make_bronze, no_pincodes):
    silver = build_silver_base(make_bronze({}), no_pincodes)

    types = {f.name: f.dataType.simpleString() for f in silver.schema.fields}
    assert {name: types[name] for name in LIST_COLUMNS} == {name: "array<string>" for name in LIST_COLUMNS}


def test_a_json_list_becomes_its_items_in_order(make_bronze, no_pincodes):
    bronze = make_bronze({"specialties": '["cardiology", "nephrology", "neurology"]'})

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.specialties == ["cardiology", "nephrology", "neurology"]


def test_a_single_email_becomes_a_one_item_list(make_bronze, no_pincodes):
    bronze = make_bronze({"email": " info@cityhospital.in "})

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.email == ["info@cityhospital.in"]


def test_an_email_list_keeps_every_address(make_bronze, no_pincodes):
    bronze = make_bronze({"email": '["info@cityhospital.in", "opd@cityhospital.in"]'})

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.email == ["info@cityhospital.in", "opd@cityhospital.in"]


def test_list_items_are_whitespace_normalized(make_bronze, no_pincodes):
    bronze = make_bronze({"procedure": '["  knee\\u00a0 replacement\\n", "\\u200bdialysis"]'})

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.procedure == ["knee replacement", "dialysis"]


def test_empty_null_and_missing_items_are_dropped(make_bronze, no_pincodes):
    bronze = make_bronze(
        {"equipment": '["", "MRI", null, "  ", "NULL", "[]", "CT scanner"]'},
        {"email": '["[email\\u00a0protected]", "info@cityhospital.in"]'},
    )

    rows = build_silver_base(bronze, no_pincodes).orderBy("unique_id").collect()

    assert (rows[0].equipment, rows[1].email) == (["MRI", "CT scanner"], ["info@cityhospital.in"])


def test_a_list_left_empty_after_cleanup_becomes_null(make_bronze, no_pincodes):
    bronze = make_bronze({"capability": '["", null, " null "]', "email": '["[email protected]"]'})

    row = build_silver_base(bronze, no_pincodes).first()

    assert (row.capability, row.email) == (None, None)


def test_duplicate_items_collapse_to_the_first_spelling_in_order(make_bronze, no_pincodes):
    bronze = make_bronze(
        {
            "procedure": (
                '["Laparoscopic Surgery", "Dialysis", "laparoscopic surgery", '
                '"Laparoscopic-Surgery", "dialysis.", "Cataract Surgery", "cataract surgerys"]'
            ),
            "equipment": '["MRI Scanner", "MRI scanners", "X-ray", "xray"]',
            "affiliationTypeIds": '["faith-tradition", "Faith Tradition", "academic"]',
        }
    )

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.procedure == ["Laparoscopic Surgery", "Dialysis", "Cataract Surgery"]
    assert row.equipment == ["MRI Scanner", "X-ray"]
    assert row.affiliation_types == ["faith-tradition", "academic"]


def test_items_differing_by_real_letters_stay_separate(make_bronze, no_pincodes):
    bronze = make_bronze(
        {
            "specialties": '["nephrology", "neurology"]',
            "procedure": '["IUI treatment", "IVF treatment", "type 1 diabetes", "type 2 diabetes"]',
        }
    )

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.specialties == ["nephrology", "neurology"]
    assert row.procedure == ["IUI treatment", "IVF treatment", "type 1 diabetes", "type 2 diabetes"]


def test_identifier_lists_dedupe_on_exact_equality_only(make_bronze, no_pincodes):
    bronze = make_bronze(
        {
            "websites": '["cityhospital.in/About", "cityhospital.in/about", "cityhospital.in/About"]',
            # Items formatting can't change, so only exact equality can merge them.
            "email": '["Reception Desk", "reception desk", "Reception Desk"]',
            "phone_numbers": '["+2382247959", "+238 2247959", "+2382247959"]',
        }
    )

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.websites == ["cityhospital.in/About", "cityhospital.in/about"]
    assert row.email == ["Reception Desk", "reception desk"]
    assert row.phone_numbers == ["+2382247959", "+238 2247959"]


def test_source_urls_are_kept_as_captured_apart_from_exact_duplicates(make_bronze, no_pincodes):
    bronze = make_bronze(
        {
            "source_urls": (
                '["https://www.CityHospital.in/About/", "https://cityhospital.in/about", '
                '"https://www.CityHospital.in/About/"]'
            )
        }
    )

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.source_urls == ["https://www.CityHospital.in/About/", "https://cityhospital.in/about"]


def _json_list(items):
    return "[" + ", ".join("null" if item is None else f'"{item}"' for item in items) + "]"


def test_a_list_at_the_50_item_cap_marks_the_facility_for_investigation(make_bronze, no_pincodes):
    bronze = make_bronze(
        {
            "capability": _json_list(f"service {n}" for n in range(50)),
            "affiliationTypeIds": _json_list(["private"] * 50),
        }
    )

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.needs_investigation is True
    assert row.truncated_columns == ["capability", "affiliation_types"]


def test_a_heavily_duplicated_50_item_list_is_still_truncated(make_bronze, no_pincodes):
    items = ["Dialysis", "dialysis", "", None, "DIALYSIS."] * 10
    bronze = make_bronze({"procedure": _json_list(items)})

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.procedure == ["Dialysis"]
    assert (row.needs_investigation, row.truncated_columns) == (True, ["procedure"])


def test_lists_below_the_cap_are_not_truncated(make_bronze, no_pincodes):
    bronze = make_bronze(
        {"specialties": _json_list(f"specialty {n}" for n in range(49)), "email": "info@cityhospital.in"},
        {},
    )

    rows = build_silver_base(bronze, no_pincodes).collect()

    assert [(row.needs_investigation, row.truncated_columns) for row in rows] == [(False, None), (False, None)]


def test_flag_columns_have_their_types(make_bronze, no_pincodes):
    silver = build_silver_base(make_bronze({}), no_pincodes)

    types = {f.name: f.dataType.simpleString() for f in silver.schema.fields}
    assert (types["needs_investigation"], types["truncated_columns"]) == ("boolean", "array<string>")


# Formatting (spec #1, "Formatting"): contact and location fields.


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("201 301", "201301"),
        ("560-001", "560001"),
        ("682016", "682016"),
        ("COCHIN-16", "COCHIN-16"),
        ("12 34", "12 34"),
    ],
)
def test_pins_with_spaces_or_hyphens_become_six_digits_and_others_are_unchanged(make_bronze, no_pincodes, raw, expected):
    row = build_silver_base(make_bronze({"address_zipOrPostcode": raw}), no_pincodes).first()

    assert row.address_pincode == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+91 98765 43210", "+919876543210"),
        ("91-98765-43210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("(022) 2345 6789", "(022) 2345 6789"),
        ("+91 1800 123 4567", "+9118001234567"),
        ("91 1860 500 1066", "+9118605001066"),
        ("+2382247959", "+2382247959"),
        ("12345", "12345"),
    ],
)
def test_phones_become_plus_91_and_ten_digits_and_others_are_unchanged(make_bronze, no_pincodes, raw, expected):
    bronze = make_bronze({"officialPhone": raw, "phone_numbers": f'["{raw}"]'})

    row = build_silver_base(bronze, no_pincodes).first()

    assert (row.official_phone, row.phone_numbers) == (expected, [expected])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Info@CityHospital.in", "info@cityhospital.in"),
        ("info[at]cityhospital[dot]in", "info@cityhospital.in"),
        ("OPD (at) cityhospital (dot) co.in", "opd@cityhospital.co.in"),
        ("care at cityhospital.org", "care@cityhospital.org"),
        ("Contact Reception", "Contact Reception"),
        ("Info[at]CityHospital", "Info[at]CityHospital"),
    ],
)
def test_emails_are_lower_cased_and_decoded_when_the_result_is_an_address(make_bronze, no_pincodes, raw, expected):
    row = build_silver_base(make_bronze({"email": f'["{raw}"]'}), no_pincodes).first()

    assert row.email == [expected]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.CityHospital.IN/", "cityhospital.in"),
        ("http://CityHospital.in/Departments/Cardiology/", "cityhospital.in/Departments/Cardiology"),
        ("WWW.Apollo.com/Find-A-Doctor?City=Pune", "apollo.com/Find-A-Doctor?City=Pune"),
        ("https://www.facebook.com/CityHospitalPune/", "facebook.com/CityHospitalPune"),
        ("infomedanta.org", "infomedanta.org"),
        ("Not Available Online", "Not Available Online"),
    ],
)
def test_urls_get_a_lower_case_host_without_scheme_www_or_trailing_slash(make_bronze, no_pincodes, raw, expected):
    bronze = make_bronze({"officialWebsite": raw, "websites": f'["{raw}"]', "facebookLink": raw})

    row = build_silver_base(bronze, no_pincodes).first()

    assert (row.official_website, row.websites, row.facebook_link) == (expected, [expected], expected)


def test_format_only_variants_collapse_to_one_item(make_bronze, no_pincodes):
    bronze = make_bronze(
        {
            "phone_numbers": '["+91 98765 43210", "098765 43210", "9876543210", "91-98765-43210"]',
            "websites": '["https://www.CityHospital.in/", "cityhospital.in", "http://cityhospital.in/About"]',
            "email": '["Info@CityHospital.in", "info[at]cityhospital[dot]in"]',
        }
    )

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.phone_numbers == ["+919876543210", "098765 43210"]
    assert row.websites == ["cityhospital.in", "cityhospital.in/About"]
    assert row.email == ["info@cityhospital.in"]


# Spelling fixes (spec #1, "Spelling fixes").


def test_facility_type_is_lower_cased_and_farmacy_becomes_pharmacy(make_bronze, no_pincodes):
    bronze = make_bronze({"facilityTypeId": "farmacy"}, {"facilityTypeId": "Hospital"}, {"facilityTypeId": "kie"})

    types = [row.facility_type for row in build_silver_base(bronze, no_pincodes).orderBy("unique_id").collect()]

    assert types == ["pharmacy", "hospital", "kie"]


def test_operator_type_is_lower_cased_and_government_becomes_public(make_bronze, no_pincodes):
    bronze = make_bronze({"operatorTypeId": "government"}, {"operatorTypeId": "Private"}, {"operatorTypeId": "kie"})

    operators = [row.operator_type for row in build_silver_base(bronze, no_pincodes).orderBy("unique_id").collect()]

    assert operators == ["public", "private", "kie"]


def test_affiliation_types_are_lower_cased_with_spelling_fixes_and_invalid_values_kept(make_bronze, no_pincodes):
    bronze = make_bronze({"affiliationTypeIds": '["Private-Entity", "academic", "NAAC", "DCI", "private"]'})

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.affiliation_types == ["private", "academic", "naac", "dci"]


def _states(make_bronze, no_pincodes, raw_states):
    bronze = make_bronze(*[{"unique_id": f"f{i:02d}", "address_stateOrRegion": s} for i, s in enumerate(raw_states)])
    return [row.address_state for row in build_silver_base(bronze, no_pincodes).orderBy("unique_id").collect()]


def test_state_typos_abbreviations_and_old_names_become_the_official_name(make_bronze, no_pincodes):
    raw = ["Tamilnadu", "U.p.", "Orissa", "Nct Of Delhi", "Uttranchal", "Uttar Prades H", "Ms", "kerala"]

    assert _states(make_bronze, no_pincodes, raw) == [
        "Tamil Nadu", "Uttar Pradesh", "Odisha", "Delhi", "Uttarakhand", "Uttar Pradesh", "Maharashtra", "Kerala",
    ]


def test_a_state_after_the_last_comma_becomes_the_state(make_bronze, no_pincodes):
    raw = ["Gurugram, Haryana", "Satara District, Maharashtra", "Jammu, J&k", "Pallikulam, Kannur District, Kerala"]

    assert _states(make_bronze, no_pincodes, raw) == ["Haryana", "Maharashtra", "Jammu And Kashmir", "Kerala"]


def test_cities_and_ambiguous_values_in_the_state_field_are_unchanged(make_bronze, no_pincodes):
    raw = ["Thane", "Mumbai", "Punjab Region", "Kashmir", "Ut", "Madhya", "Tamil Nadu; Karnataka", "Kerala, Thrissur"]

    assert _states(make_bronze, no_pincodes, raw) == raw


def test_city_is_title_cased_and_old_names_become_current_ones(make_bronze, no_pincodes):
    raw = ["Bangalore", "GURGAON", "bombay", "navi mumbai", "Trivandrum", "Pune"]
    bronze = make_bronze(*[{"unique_id": f"f{i}", "address_city": c} for i, c in enumerate(raw)])

    cities = [row.address_city for row in build_silver_base(bronze, no_pincodes).orderBy("unique_id").collect()]

    assert cities == ["Bengaluru", "Gurugram", "Mumbai", "Navi Mumbai", "Thiruvananthapuram", "Pune"]


def test_british_specialty_spellings_become_american_keeping_their_case_shape(make_bronze, no_pincodes):
    bronze = make_bronze(
        {
            "specialties": (
                '["paediatricCardiology", "clinicalHaematology", "orthopaedicSurgery", "obstetricsAndGynaecology", '
                '"neuroAnaesthesiology", "Oesophageal Surgery", "lymphoedema", "PAEDIATRICS & NEONATOLOGY"]'
            )
        }
    )

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.specialties == [
        "pediatricCardiology", "clinicalHematology", "orthopedicSurgery", "obstetricsAndGynecology",
        "neuroAnesthesiology", "Esophageal Surgery", "lymphedema", "PEDIATRICS & NEONATOLOGY",
    ]


def test_specialty_spelling_fixes_run_before_duplicate_removal(make_bronze, no_pincodes):
    bronze = make_bronze({"specialties": '["pediatricSurgery", "paediatricSurgery", "Haematology", "hematology"]'})

    row = build_silver_base(bronze, no_pincodes).first()

    assert row.specialties == ["pediatricSurgery", "Hematology"]


# State checked against the pincode directory (#9).


def _checked(make_bronze, make_pincodes, facilities, offices):
    """Silver base `(address_state, flags)` per Facility, flags as the set of names set true."""
    bronze = make_bronze(*[{"unique_id": f"f{i:02d}", **f} for i, f in enumerate(facilities)])
    rows = build_silver_base(bronze, make_pincodes(*offices)).orderBy("unique_id").collect()
    flags = ["flag_state_corrected", "flag_pin_mismatch", "flag_address_conflict", "flag_pin_unverified"]
    return [(row.address_state, {f for f in flags if row[f]}) for row in rows]


def test_a_state_conflicting_with_its_pin_takes_the_city_state_when_the_pin_agrees(make_bronze, make_pincodes):
    facilities = [
        {"address_city": "Hyderabad", "address_stateOrRegion": "Andhra Pradesh", "address_zipOrPostcode": "500 001"},
        {"address_city": "Panchkula", "address_stateOrRegion": "Chandigarh", "address_zipOrPostcode": "134109"},
    ]
    offices = [
        (500001, "HYDERABAD", "TELANGANA"),
        (134109, "PANCHKULA", "HARYANA"),
        (134110, "Panchkula", "HARYANA"),
    ]

    assert _checked(make_bronze, make_pincodes, facilities, offices) == [
        ("Telangana", {"flag_state_corrected"}),
        ("Haryana", {"flag_state_corrected"}),
    ]


def test_a_state_conflicting_with_its_pin_is_kept_as_a_pin_mismatch_when_the_city_agrees_with_it(
    make_bronze, make_pincodes
):
    facilities = [{"address_city": "Nagpur", "address_stateOrRegion": "Maharashtra", "address_zipOrPostcode": "682016"}]
    offices = [(682016, "ERNAKULAM", "KERALA"), (440001, "NAGPUR", "MAHARASHTRA")]

    assert _checked(make_bronze, make_pincodes, facilities, offices) == [("Maharashtra", {"flag_pin_mismatch"})]


def test_a_state_conflicting_with_its_pin_is_kept_as_an_address_conflict_when_the_city_cannot_settle_it(
    make_bronze, make_pincodes
):
    facilities = [
        # Border area: the city's district is in two states.
        {"address_city": "Faridabad", "address_stateOrRegion": "Delhi", "address_zipOrPostcode": "121001"},
        # City is not a district at all.
        {"address_city": "Sector 5", "address_stateOrRegion": "Delhi", "address_zipOrPostcode": "121001"},
        # City names a third state, neither A nor in P.
        {"address_city": "Patna", "address_stateOrRegion": "Delhi", "address_zipOrPostcode": "121001"},
        # No city.
        {"address_stateOrRegion": "Delhi", "address_zipOrPostcode": "121001"},
    ]
    offices = [
        (121001, "FARIDABAD", "HARYANA"),
        (110044, "Faridabad", "DELHI"),
        (800001, "PATNA", "BIHAR"),
    ]

    assert _checked(make_bronze, make_pincodes, facilities, offices) == [("Delhi", {"flag_address_conflict"})] * 4


def test_a_pin_that_cannot_be_checked_keeps_the_state_and_is_flagged_unverified(make_bronze, make_pincodes):
    kerala = {"address_city": "Kochi", "address_stateOrRegion": "Kerala"}
    facilities = [
        {**kerala, "address_zipOrPostcode": "999999"},  # not in the directory
        {**kerala, "address_zipOrPostcode": "682016"},  # directory state NA only
        {**kerala, "address_zipOrPostcode": None},  # missing: nothing to check
        {**kerala, "address_zipOrPostcode": "COCHIN-16"},  # malformed: nothing to check
    ]
    offices = [(682016, "ERNAKULAM", "NA"), (682017, "Kochi", "KERALA")]

    assert _checked(make_bronze, make_pincodes, facilities, offices) == [
        ("Kerala", {"flag_pin_unverified"}),
        ("Kerala", {"flag_pin_unverified"}),
        ("Kerala", set()),
        ("Kerala", set()),
    ]


def test_a_state_agreeing_with_any_of_its_pins_states_is_unchanged(make_bronze, make_pincodes):
    facilities = [
        {"address_city": "Hyderabad", "address_stateOrRegion": "telangana", "address_zipOrPostcode": "500001"},
        # A multi-state PIN agrees with each of its states, and ignores NA.
        {"address_city": "Chandigarh", "address_stateOrRegion": "Punjab", "address_zipOrPostcode": "160001"},
        {"address_city": "Chandigarh", "address_stateOrRegion": "Chandigarh", "address_zipOrPostcode": "160001"},
    ]
    offices = [
        (500001, "HYDERABAD", "TELANGANA"),
        (160001, "CHANDIGARH", "CHANDIGARH"),
        (160001, "MOHALI", "PUNJAB"),
        (160001, "MOHALI", "NA"),
    ]

    assert _checked(make_bronze, make_pincodes, facilities, offices) == [
        ("Telangana", set()),
        ("Punjab", set()),
        ("Chandigarh", set()),
    ]


def test_a_missing_or_unofficial_state_is_never_checked(make_bronze, make_pincodes):
    facilities = [
        {"address_city": "Hyderabad", "address_stateOrRegion": None, "address_zipOrPostcode": "500001"},
        {"address_city": "Hyderabad", "address_stateOrRegion": "Thane", "address_zipOrPostcode": "500001"},
        {"address_city": "Hyderabad", "address_stateOrRegion": "Thane", "address_zipOrPostcode": "999999"},
    ]
    offices = [(500001, "HYDERABAD", "TELANGANA")]

    assert _checked(make_bronze, make_pincodes, facilities, offices) == [
        (None, set()),
        ("Thane", set()),
        ("Thane", set()),
    ]


def test_the_state_check_never_changes_the_pin(make_bronze, make_pincodes):
    bronze = make_bronze(
        {"address_city": "Hyderabad", "address_stateOrRegion": "Andhra Pradesh", "address_zipOrPostcode": "500 001"}
    )

    row = build_silver_base(bronze, make_pincodes((500001, "HYDERABAD", "TELANGANA"))).first()

    assert (row.address_state, row.address_pincode) == ("Telangana", "500001")


def test_state_check_flags_are_booleans(make_bronze, no_pincodes):
    silver = build_silver_base(make_bronze({}), no_pincodes)

    types = {f.name: f.dataType.simpleString() for f in silver.schema.fields}
    flags = ["flag_state_corrected", "flag_pin_mismatch", "flag_address_conflict", "flag_pin_unverified"]
    assert [types[f] for f in flags] == ["boolean"] * 4
