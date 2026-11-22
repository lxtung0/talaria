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
        ("flag_official_phone_not_in_list", "boolean"),
        ("flag_phone_list_without_official", "boolean"),
        ("flag_official_website_not_in_list", "boolean"),
        ("flag_bed_doctor_ratio_outlier", "boolean"),
        ("flag_affiliation_operator_conflict", "boolean"),
        ("primary_affiliation", "string"),
        ("flag_page_update_unparsable", "boolean"),
        ("flag_future_page_update", "boolean"),
    ]


# A. Contact consistency: case -> (official value, list, flag).
OFFICIAL_PHONES = {
    "in the list": ("98765 43210", '["+91 91234 56789", "+91-98765-43210"]', False),
    "same last 10 digits, other prefix": ("+91 98765 43210", '["098765 43210"]', False),
    "not in the list": ("98765 43210", '["91234 56789"]', True),
    "no list": ("98765 43210", None, True),
    "fewer than 10 digits, in the list": ("2345678", '["234-5678"]', False),
    "fewer than 10 digits, only a suffix of an item": ("2345678", '["9112345678"]', True),
    "no official phone": (None, '["91234 56789"]', False),
    "no digits to compare": ("call us", '["91234 56789"]', False),
    "neither": (None, None, False),
}


def test_official_phone_not_in_list(build):
    rows = build(
        *[
            {"unique_id": case, "officialPhone": phone, "phone_numbers": phones}
            for case, (phone, phones, _) in OFFICIAL_PHONES.items()
        ]
    )

    actual = {case: rows[case].flag_official_phone_not_in_list for case in OFFICIAL_PHONES}
    assert actual == {case: flag for case, (*_, flag) in OFFICIAL_PHONES.items()}


def test_phone_list_without_official(build):
    rows = build(
        {"unique_id": "list only", "phone_numbers": '["98765 43210"]'},
        {"unique_id": "both", "officialPhone": "98765 43210", "phone_numbers": '["98765 43210"]'},
        {"unique_id": "official only", "officialPhone": "98765 43210"},
        {"unique_id": "neither"},
        {"unique_id": "empty list", "phone_numbers": "[]"},
    )

    assert {case: row.flag_phone_list_without_official for case, row in rows.items()} == {
        "list only": True, "both": False, "official only": False, "neither": False, "empty list": False,
    }


OFFICIAL_WEBSITES = {
    "same URL": ("https://www.city.org", '["city.org"]', False),
    "same host, different path": ("city.org/contact", '["facebook.com/city", "http://City.org/About?x=1"]', False),
    "same host, with a port": ("city.org:8080", '["city.org"]', False),
    "not in the list": ("city.org", '["other.org/city.org"]', True),
    "subdomain is another host": ("city.org", '["book.city.org"]', True),
    "no list": ("city.org", None, True),
    "no official website": (None, '["city.org"]', False),
    "no host to compare": ("/contact", '["city.org"]', False),
    "same text that is not a host": ("unknown", '["city.org", "unknown"]', False),
    "broken host": ("city hospital.org", '["cityhospital.org"]', True),
    "neither": (None, None, False),
}


def test_official_website_not_in_list(build):
    rows = build(
        *[
            {"unique_id": case, "officialWebsite": website, "websites": websites}
            for case, (website, websites, _) in OFFICIAL_WEBSITES.items()
        ]
    )

    actual = {case: rows[case].flag_official_website_not_in_list for case in OFFICIAL_WEBSITES}
    assert actual == {case: flag for case, (*_, flag) in OFFICIAL_WEBSITES.items()}


# B. Size consistency.
def _sized(prefix, facility_type, ratios):
    """One Facility per ratio, with 1 doctor and that many beds."""
    return [
        {"unique_id": f"{prefix}{i}", "facilityTypeId": facility_type, "capacity": str(beds), "numberDoctors": "1"}
        for i, beds in enumerate(ratios)
    ]


def _outliers(rows):
    return {unique_id for unique_id, row in rows.items() if row.flag_bed_doctor_ratio_outlier}


def test_ratio_outside_the_types_percentiles_is_an_outlier(build):
    # Hospital ratios 100..200 have percentiles 101 and 199, which are inside the range.
    # Among all Facilities the range would differ: 101 would be out and 200 in.
    rows = build(*_sized("h", "hospital", range(100, 201)), *_sized("c", "clinic", [1000] * 50))

    assert _outliers(rows) == {"h0", "h100"}


@pytest.mark.parametrize(
    "facility_type, checkable, flagged",
    [
        ("clinic", 50, True),  # its own range: nearly all 150, so 199 is out
        ("clinic", 49, False),  # the range of all Facilities: 199 is in
        (None, 50, False),  # no type: the range of all Facilities, however many there are
    ],
)
def test_small_or_missing_type_uses_all_facilities(build, facility_type, checkable, flagged):
    uncheckable = [
        {"unique_id": f"u{i}", "facilityTypeId": facility_type, "capacity": "150"} for i in range(10)
    ]
    rows = build(
        *_sized("h", "hospital", range(100, 201)),
        *_sized("c", facility_type, [150] * (checkable - 1) + [199]),
        *uncheckable,  # don't count towards the 50
    )

    assert rows[f"c{checkable - 1}"].flag_bed_doctor_ratio_outlier is flagged


@pytest.mark.parametrize("ansi", ["false", "true"])
def test_ratio_that_cannot_be_checked_is_false_and_ignored(build, spark, ansi):
    uncheckable = {
        "no beds": (None, "1"),
        "zero beds": ("0", "1"),
        "negative beds": ("-5", "1"),
        "no doctors": ("9000", None),
        "zero doctors": ("9000", "0"),
        "negative doctors": ("9000", "-1"),
        "neither": (None, None),
    }
    previous = spark.conf.get("spark.sql.ansi.enabled", "false")
    spark.conf.set("spark.sql.ansi.enabled", ansi)
    try:
        rows = build(
            *_sized("h", "hospital", range(100, 201)),
            *[
                {"unique_id": case, "facilityTypeId": "hospital", "capacity": beds, "numberDoctors": doctors}
                for case, (beds, doctors) in uncheckable.items()
            ],
        )
    finally:
        spark.conf.set("spark.sql.ansi.enabled", previous)

    assert _outliers(rows) == {"h0", "h100"}


def test_no_checkable_ratio_at_all_is_false(build):
    rows = build({"facilityTypeId": "hospital", "capacity": "100"}, {})

    assert len(rows) == 2 and not _outliers(rows)


def test_more_doctors_than_beds_is_not_flagged_on_its_own(build):
    rows = build({"facilityTypeId": "hospital", "capacity": "5", "numberDoctors": "20"})

    assert not _outliers(rows)


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
