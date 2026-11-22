"""Silver NFHS-5 (#41), tested through `build_silver_nfhs5` on small fake bronze tables."""

import datetime

import pytest
from pyspark.sql import functions as F
from pyspark.sql import types as T

from talaria.silver_nfhs5 import build_silver_nfhs5
from talaria.silver_nfhs5.checks import check_silver_nfhs5
from talaria.silver_nfhs5.marker_counts import format_marker_counts, marker_counts

# A few real NFHS-5 column names, in source order: key, survey sizes, indicators.
INDICATORS = [
    "institutional_birth_5y_pct",
    "child_12_23m_who_have_received_bcg_pct",
    "average_out_of_pocket_expenditure_per_delivery_in_a_public_fac",
]
SOURCE_COLUMNS = [
    "district_name", "state_ut", "households_surveyed", "women_15_49_interviewed", "men_15_54_interviewed",
    *INDICATORS,
]
BRONZE_SCHEMA = T.StructType(
    [T.StructField(name, T.StringType()) for name in SOURCE_COLUMNS]
    + [T.StructField("_source_table", T.StringType()), T.StructField("_ingested_at", T.TimestampType())]
)


@pytest.fixture
def make_bronze(spark):
    """A bronze NFHS-5 table from partial rows; every unset value is a plain number."""

    def build(*rows):
        records = []
        for i, row in enumerate(rows):
            record = {
                "district_name": f"District {i}",
                "state_ut": "Kerala",
                "households_surveyed": "900",
                "women_15_49_interviewed": "800",
                "men_15_54_interviewed": "120",
                **{name: "50.0" for name in INDICATORS},
                "_source_table": "nfhs_5_district_health_indicators",
                "_ingested_at": datetime.datetime(2026, 11, 22),
                **row,
            }
            records.append(tuple(record[name] for name in BRONZE_SCHEMA.fieldNames()))
        return spark.createDataFrame(records, BRONZE_SCHEMA)

    return build


@pytest.fixture
def build(make_bronze):
    """Silver rows in input order, after the runtime checks pass."""

    def run(*rows):
        bronze = make_bronze(*rows)
        silver = build_silver_nfhs5(bronze)
        check_silver_nfhs5(bronze, silver)
        return silver.collect()

    return run


def test_keeps_every_source_column_then_adds_the_marker_lists(make_bronze):
    bronze = make_bronze({})
    silver = build_silver_nfhs5(bronze)

    assert silver.columns == [*bronze.columns, "suppressed_columns", "low_sample_columns"]
    types = dict(silver.dtypes)
    assert types["households_surveyed"] == "int"
    assert all(types[name] == "double" for name in INDICATORS)
    assert types["_ingested_at"] == "timestamp"


def test_values_are_trimmed_and_typed(build):
    [row] = build({"households_surveyed": " 874 ", "institutional_birth_5y_pct": "97.8 ",
                   "average_out_of_pocket_expenditure_per_delivery_in_a_public_fac": "2278"})

    assert row.households_surveyed == 874
    assert row.institutional_birth_5y_pct == 97.8
    assert row.average_out_of_pocket_expenditure_per_delivery_in_a_public_fac == 2278.0
    assert (row.suppressed_columns, row.low_sample_columns) == (None, None)


def test_markers_are_unwrapped_and_listed(build):
    [row] = build(
        {
            "institutional_birth_5y_pct": "*",
            "child_12_23m_who_have_received_bcg_pct": "(80.4)",
            "average_out_of_pocket_expenditure_per_delivery_in_a_public_fac": " (3460) ",
        }
    )

    assert row.institutional_birth_5y_pct is None
    assert row.child_12_23m_who_have_received_bcg_pct == 80.4
    assert row.average_out_of_pocket_expenditure_per_delivery_in_a_public_fac == 3460.0
    assert row.suppressed_columns == ["institutional_birth_5y_pct"]
    assert row.low_sample_columns == [
        "child_12_23m_who_have_received_bcg_pct",
        "average_out_of_pocket_expenditure_per_delivery_in_a_public_fac",
    ]


def test_a_blank_indicator_is_null_without_a_marker(build):
    [row] = build({"institutional_birth_5y_pct": "  "})

    assert row.institutional_birth_5y_pct is None
    assert row.suppressed_columns is None


# NFHS-5 state spelling -> the project's official name.
STATES = {
    "Maharastra": "Maharashtra",
    "NCT of Delhi": "Delhi",
    "Jammu & Kashmir": "Jammu And Kashmir",
    "Andaman & Nicobar Islands": "Andaman And Nicobar Islands",
    "Dadra and Nagar Haveli & Daman and Diu": "The Dadra And Nagar Haveli And Daman And Diu",
    " Lakshadweep ": "Lakshadweep",
    "Tamil Nadu": "Tamil Nadu",
}


def test_states_become_official_names(build):
    rows = build(*[{"state_ut": state} for state in STATES])

    assert [row.state_ut for row in rows] == list(STATES.values())


def test_district_names_are_trimmed_but_not_renamed(build):
    rows = build({"district_name": " North &  Middle Andaman "}, {"district_name": "Bangalore"})

    assert [row.district_name for row in rows] == ["North & Middle Andaman", "Bangalore"]


def test_the_same_district_name_in_two_states_is_two_districts(build):
    rows = build(
        {"district_name": "Aurangabad", "state_ut": "Bihar"},
        {"district_name": "Aurangabad", "state_ut": "Maharastra"},
    )

    assert [(row.state_ut, row.district_name) for row in rows] == [
        ("Bihar", "Aurangabad"),
        ("Maharashtra", "Aurangabad"),
    ]


@pytest.mark.parametrize(
    "row, message",
    [
        ({"state_ut": "Atlantis"}, r"state_ut/district_name: 1 row\(s\) NULL"),
        ({"institutional_birth_5y_pct": "97.8%"}, r"institutional_birth_5y_pct: 1 value\(s\) that aren't a number"),
        ({"institutional_birth_5y_pct": "NA"}, r"institutional_birth_5y_pct: 1 value\(s\) that aren't a number"),
        ({"households_surveyed": None}, r"households_surveyed: 1 row\(s\) NULL"),
    ],
)
def test_checks_fail_on_values_cleaning_cant_explain(make_bronze, row, message):
    bronze = make_bronze(row)

    with pytest.raises(ValueError, match=message):
        check_silver_nfhs5(bronze, build_silver_nfhs5(bronze))


def test_checks_fail_on_a_repeated_district(make_bronze):
    bronze = make_bronze({"district_name": "Kollam"}, {"district_name": " Kollam"})

    with pytest.raises(ValueError, match=r"is repeated: 1 distinct"):
        check_silver_nfhs5(bronze, build_silver_nfhs5(bronze))


def test_checks_fail_on_a_lost_row(make_bronze):
    bronze = make_bronze({}, {})

    with pytest.raises(ValueError, match=r"row count is 1, bronze has 2"):
        check_silver_nfhs5(bronze, build_silver_nfhs5(bronze).limit(1))


def test_marker_counts(make_bronze):
    silver = build_silver_nfhs5(
        make_bronze(
            {"institutional_birth_5y_pct": "*", "child_12_23m_who_have_received_bcg_pct": "(80.4)"},
            {"institutional_birth_5y_pct": "*"},
        )
    )

    counts = marker_counts(silver)

    assert counts == {
        "institutional_birth_5y_pct": {"suppressed": 2, "low_sample": 0},
        "child_12_23m_who_have_received_bcg_pct": {"suppressed": 0, "low_sample": 1},
    }
    assert "institutional_birth_5y_pct" in format_marker_counts(counts)


def test_reads_any_bronze_column_type(make_bronze):
    """The source table may type some columns; everything is read through its text."""
    bronze = make_bronze({}).withColumn("households_surveyed", F.lit(874).cast("int"))
    silver = build_silver_nfhs5(bronze)
    check_silver_nfhs5(bronze, silver)

    assert silver.first().households_surveyed == 874


def test_reads_survey_sizes_from_a_double_column(make_bronze):
    """On Databricks the source types the survey sizes as `double`, which read as `882.0`."""
    bronze = make_bronze({}).withColumn("households_surveyed", F.lit(882.0).cast("double"))
    silver = build_silver_nfhs5(bronze)
    check_silver_nfhs5(bronze, silver)

    assert silver.first().households_surveyed == 882
