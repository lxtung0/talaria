"""Group F, source quality flags (spec #13, #15), tested only through `build_silver_facilities`."""

import datetime
import json

import pytest

from talaria.silver_facilities import build_silver_facilities

RUN_DATE = datetime.date(2026, 11, 21)
F_FLAGS = [
    "flag_has_government_source",
    "flag_own_site_in_sources",
    "flag_only_directory_sources",
    "flag_single_source_domain",
]


@pytest.fixture
def flags(make_silver_inputs, no_pincodes):
    """Group F flags by `unique_id`, as a dict of flag name -> value."""

    def run(*rows):
        bronze, silver_base = make_silver_inputs(*rows)
        facilities = build_silver_facilities(silver_base, bronze, no_pincodes, RUN_DATE)
        return {row.unique_id: {name: row[name] for name in F_FLAGS} for row in facilities.collect()}

    return run


def sources(unique_id, *urls, website=None):
    row = {"unique_id": unique_id, "source_urls": json.dumps(list(urls))}
    if website is not None:
        row["officialWebsite"] = website
    return row


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://health.delhi.gov.in/hospitals", True),
        ("http://amritsar.nic.in/public-utility/x", True),
        ("https://www.cdc.gov/page", True),
        ("https://notgov.in/page", False),
        ("https://gov.in.example.com/page", False),
        ("https://www.practo.com/delhi/hospital", False),
    ],
)
def test_government_source(flags, url, expected):
    result = flags(sources("a", url, "https://www.justdial.com/x"))

    assert result["a"]["flag_has_government_source"] is expected


def test_own_site_among_sources_matches_on_host(flags):
    result = flags(
        sources("own", "https://www.CityHospital.in/contact", "https://practo.com/x", website="https://cityhospital.in/home"),
        sources("other", "https://practo.com/x", website="cityhospital.in"),
        sources("no-website", "https://cityhospital.in/contact"),
    )

    assert result["own"]["flag_own_site_in_sources"] is True
    assert result["other"]["flag_own_site_in_sources"] is False
    assert result["no-website"]["flag_own_site_in_sources"] is False


def test_only_directory_and_social_sources(flags):
    result = flags(
        sources("listings", "https://www.practo.com/x", "https://m.facebook.com/y", "https://in.linkedin.com/company/z"),
        sources("with-own-site", "https://www.practo.com/x", "https://cityhospital.in/about"),
        sources("government", "https://www.justdial.com/x", "https://health.delhi.gov.in/list"),
    )

    assert result["listings"]["flag_only_directory_sources"] is True
    assert result["with-own-site"]["flag_only_directory_sources"] is False
    assert result["government"]["flag_only_directory_sources"] is False


def test_directory_match_needs_a_whole_host_label(flags):
    # `notpractocom.in` and `practo.com.fake.in` are not practo.com.
    result = flags(sources("lookalike", "https://notpractocom.in/x", "https://practo.com.fake.in/y"))

    assert result["lookalike"]["flag_only_directory_sources"] is False


def test_single_source_domain(flags):
    result = flags(
        sources("one-host", "https://practo.com/a", "http://www.practo.com/b?x=1"),
        sources("two-hosts", "https://practo.com/a", "https://justdial.com/b"),
    )

    assert result["one-host"]["flag_single_source_domain"] is True
    assert result["two-hosts"]["flag_single_source_domain"] is False


def test_no_sources_gives_all_flags_false(flags):
    # An empty list is a Missing value: Silver base keeps the Facility with NULL `source_urls`.
    result = flags(sources("empty", website="cityhospital.in"))

    assert result["empty"] == {name: False for name in F_FLAGS}


def test_items_without_a_host_are_ignored(flags):
    result = flags(
        sources("junk-only", "not a url", "mailto:info"),
        sources("junk-and-one", "not a url", "https://practo.com/x"),
    )

    assert result["junk-only"] == {name: False for name in F_FLAGS}
    assert result["junk-and-one"]["flag_single_source_domain"] is True
    assert result["junk-and-one"]["flag_only_directory_sources"] is True


def test_source_flags_are_never_null(make_silver_inputs, no_pincodes):
    bronze, silver_base = make_silver_inputs(sources("a"), sources("b", "https://practo.com/x"), {"unique_id": "c"})

    facilities = build_silver_facilities(silver_base, bronze, no_pincodes, RUN_DATE)

    for name in F_FLAGS:
        assert facilities.where(facilities[name].isNull()).count() == 0
