"""Shared pytest fixtures: a laptop Spark session and a fake bronze facilities builder."""

import datetime
import itertools

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import types as T

# Bronze facilities schema: the source `facilities` table (every column is text
# apart from latitude/longitude) plus the two columns the bronze ingest adds.
_SOURCE_COLUMNS = [
    "unique_id", "source_types", "source_ids", "source_content_id", "name",
    "organization_type", "content_table_id", "phone_numbers", "officialPhone",
    "email", "websites", "officialWebsite", "yearEstablished", "acceptsVolunteers",
    "facebookLink", "address_line1", "address_line2", "address_line3",
    "address_city", "address_stateOrRegion", "address_zipOrPostcode",
    "address_country", "address_countryCode", "countries", "facilityTypeId",
    "operatorTypeId", "affiliationTypeIds", "description", "area",
    "numberDoctors", "capacity", "specialties", "procedure", "equipment",
    "capability", "recency_of_page_update", "distinct_social_media_presence_count",
    "affiliated_staff_presence", "custom_logo_presence",
    "number_of_facts_about_the_organization",
    "post_metrics_most_recent_social_media_post_date", "post_metrics_post_count",
    "engagement_metrics_n_followers", "engagement_metrics_n_likes",
    "engagement_metrics_n_engagements", "source", "coordinates", "latitude",
    "longitude", "cluster_id", "source_urls",
]
_DOUBLE_COLUMNS = {"latitude", "longitude"}

BRONZE_SCHEMA = T.StructType(
    [
        T.StructField(name, T.DoubleType() if name in _DOUBLE_COLUMNS else T.StringType())
        for name in _SOURCE_COLUMNS
    ]
    + [
        T.StructField("_source_table", T.StringType()),
        T.StructField("_ingested_at", T.TimestampType()),
    ]
)

_SOURCE_TABLE = "databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities"
_INGESTED_AT = datetime.datetime(2026, 11, 21, 12, 0, 0)


@pytest.fixture(scope="session")
def spark():
    session = (
        SparkSession.builder.master("local[1]")
        .appName("talaria-tests")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    yield session
    session.stop()


@pytest.fixture
def make_bronze(spark):
    """Build a fake bronze facilities DataFrame from a few partial rows.

    Each row is a dict of only the columns the test cares about. Every other
    column defaults to NULL, except that each row gets a distinct `unique_id`
    and a non-null `source_urls` (so it is a real Facility, not a Description
    fragment) unless the test sets them.

        bronze = make_bronze({"name": "City Hospital"}, {"source_urls": None})
    """
    ids = itertools.count(1)

    def build(*rows):
        records = []
        for row in rows:
            unknown = set(row) - set(BRONZE_SCHEMA.fieldNames())
            assert not unknown, f"not bronze columns: {unknown}"
            record = {
                "unique_id": f"facility-{next(ids)}",
                "source_urls": '["https://example.org/facility"]',
                "_source_table": _SOURCE_TABLE,
                "_ingested_at": _INGESTED_AT,
                **row,
            }
            records.append(tuple(record.get(name) for name in BRONZE_SCHEMA.fieldNames()))
        return spark.createDataFrame(records, BRONZE_SCHEMA)

    return build
