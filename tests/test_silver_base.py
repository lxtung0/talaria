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
