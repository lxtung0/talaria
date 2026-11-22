"""Gold district cells: H3 res-5 cell -> NFHS-5 district (the one most of its post offices are in)
-> the indicators the care finder shows."""

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

# The NFHS-5 indicators the app shows, as `{output column: Silver NFHS-5 column}`.
INDICATORS = {"insurance_pct": "hh_member_covered_health_insurance_pct"}

# Offices outside this box have bad coordinates (same box as the app's `_IN_INDIA`).
LAT_RANGE, LON_RANGE = (6, 38), (68, 98)

OUTPUT_COLUMNS = [
    "h3_r5",
    "nfhs_state",
    "nfhs_district",
    "district_share",
    "district_approximate",
    *INDICATORS,
    *[f"{name}_low_sample" for name in INDICATORS],
]


def build_district_cells(offices: DataFrame, silver_nfhs5: DataFrame) -> DataFrame:
    """One row per cell with at least one post office: `OUTPUT_COLUMNS`.

    - `nfhs_district`: the district most of the cell's offices are in (ties: by state, then name).
    - `district_share`: that district's share of the cell's offices; below 1 on a district border.
    - `district_approximate`: any of those offices reached the district through an approximate alias
      (a district carved out after NFHS-5).
    - Each indicator as Silver NFHS-5 has it (NULL when suppressed), and `<name>_low_sample`
      when NFHS-5 marked it as based on 25-49 cases.
    """
    in_india = F.col("office_lat").between(*LAT_RANGE) & F.col("office_lon").between(*LON_RANGE)
    per_district = (
        offices.where(in_india & F.col("h3_r5").isNotNull())
        .groupBy("h3_r5", "nfhs_state", "nfhs_district")
        .agg(F.count(F.lit(1)).alias("_offices"), F.max(F.col("approximate").cast("int")).alias("_approximate"))
    )
    cell = Window.partitionBy("h3_r5")
    majority = (
        per_district.withColumn("_total", F.sum("_offices").over(cell))
        .withColumn("_rank", F.row_number().over(cell.orderBy(F.desc("_offices"), "nfhs_state", "nfhs_district")))
        .where("_rank = 1")
    )
    low_sample = F.coalesce(F.col("low_sample_columns"), F.array().cast("array<string>"))
    indicators = silver_nfhs5.select(
        F.col("state_ut").alias("nfhs_state"),
        F.col("district_name").alias("nfhs_district"),
        *[F.col(source).alias(name) for name, source in INDICATORS.items()],
        *[F.array_contains(low_sample, source).alias(f"{name}_low_sample") for name, source in INDICATORS.items()],
    )
    return (
        majority.join(indicators, ["nfhs_state", "nfhs_district"], "left")
        .withColumns(
            {
                "district_share": F.round(F.col("_offices") / F.col("_total"), 3),
                "district_approximate": F.col("_approximate") == 1,
            }
        )
        .select(*OUTPUT_COLUMNS)
    )
