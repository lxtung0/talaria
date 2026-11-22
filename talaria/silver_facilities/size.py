"""Group B, size consistency (spec #13): beds per doctor against the facility type's usual range."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

# D1: the usual range is the 1st to 99th percentile, both included.
_LOW, _HIGH = 0.01, 0.99
# A type with fewer checkable Facilities than this uses the range of all Facilities.
_MIN_TYPE_SIZE = 50


def add_columns(df: DataFrame) -> DataFrame:
    """Percentiles are exact and interpolated linearly (Spark `percentile`).

    A Facility with no type uses the range of all Facilities.
    """
    beds, doctors = F.col("bed_count"), F.col("number_doctors")
    df = df.withColumn("_ratio", F.when((beds > 0) & (doctors > 0), beds / doctors))

    low, high = F.percentile("_ratio", _LOW), F.percentile("_ratio", _HIGH)
    by_type = (
        df.where(F.col("facility_type").isNotNull())
        .groupBy("facility_type")
        .agg(F.count("_ratio").alias("_checkable"), low.alias("_type_low"), high.alias("_type_high"))
        .where(F.col("_checkable") >= _MIN_TYPE_SIZE)
    )
    overall = df.agg(low.alias("_all_low"), high.alias("_all_high"))

    ratio = F.col("_ratio")
    outside = (ratio < F.coalesce("_type_low", "_all_low")) | (ratio > F.coalesce("_type_high", "_all_high"))
    return (
        df.join(F.broadcast(by_type), "facility_type", "left")
        .crossJoin(F.broadcast(overall))
        .withColumn("flag_bed_doctor_ratio_outlier", F.coalesce(outside, F.lit(False)))
        .drop("_ratio", "_checkable", "_type_low", "_type_high", "_all_low", "_all_high")
    )
