"""Shared pytest fixtures: a laptop Spark session and a fake bronze facilities builder."""

import datetime
import itertools
import os

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import types as T

from talaria.silver_base import build_silver_base

# Tests never send MLflow traces; tests/test_care_finder_tracing.py fakes the tracer.
os.environ.setdefault("TALARIA_TRACING", "0")

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
        # Adaptive query execution only re-plans for big data; on tiny fixtures it is overhead.
        .config("spark.sql.adaptive.enabled", "false")
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


# Bronze pincode directory schema: the source table plus the bronze ingest columns.
PINCODES_SCHEMA = T.StructType(
    [
        T.StructField(name, T.LongType() if name == "pincode" else T.StringType())
        for name in [
            "circlename", "regionname", "divisionname", "officename", "pincode",
            "officetype", "delivery", "district", "statename", "latitude", "longitude",
        ]
    ]
    + [
        T.StructField("_source_table", T.StringType()),
        T.StructField("_ingested_at", T.TimestampType()),
    ]
)


@pytest.fixture(scope="session")
def make_pincodes(spark):
    """Build a fake bronze pincode directory from `(pincode, district, statename)` post offices.

    An office may add `latitude, longitude` (stored as text, like the source, so
    `"NA"` works too); without them both are NULL.

        pincodes = make_pincodes((500001, "HYDERABAD", "TELANGANA"))
        pincodes = make_pincodes((500001, "HYDERABAD", "TELANGANA", 17.385, 78.4867))
    """

    def build(*offices):
        records = []
        for i, (pincode, district, state, *coordinates) in enumerate(offices):
            latitude, longitude = coordinates or (None, None)
            records.append(
                {
                    "pincode": pincode,
                    "district": district,
                    "statename": state,
                    "officename": f"Office {i}",
                    "latitude": None if latitude is None else str(latitude),
                    "longitude": None if longitude is None else str(longitude),
                }
            )
        return spark.createDataFrame(
            [tuple(r.get(name) for name in PINCODES_SCHEMA.fieldNames()) for r in records], PINCODES_SCHEMA
        )

    return build


@pytest.fixture(scope="session")
def no_pincodes(make_pincodes):
    """An empty pincode directory, for tests that don't exercise the state check."""
    return make_pincodes()


@pytest.fixture
def make_silver_inputs(make_bronze, no_pincodes):
    """Matching `(bronze, silver_base)` inputs for Silver facilities, from partial bronze rows.

    Silver base is the real `build_silver_base` output, materialized as the notebook
    reads it from a table. Pass `pincodes` when the state check matters.

        bronze, silver_base = make_silver_inputs({"officialPhone": "98765 43210"})
    """

    def build(*rows, pincodes=None):
        bronze = make_bronze(*rows)
        silver_base = build_silver_base(bronze, no_pincodes if pincodes is None else pincodes)
        return bronze, silver_base.localCheckpoint()

    return build
