"""Step 4, R1-R5: the large hospital funnel (#35). Needs steps 1-3."""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_stage3 import text

VETERINARY = r"veterin|\bpet\b|animal|\bvet\b"
TRADITIONAL = r"ayurved|homoeopath|homeopath|unani|siddha|naturopath|yoga"


def steps() -> dict[str, Column]:
    """What a row must pass at each funnel step; R1 is "not veterinary"."""
    beds, doctors = F.col("bed_count"), F.col("number_doctors")
    conditions = {
        "R1": ~F.col("is_veterinary"),
        "R2": (F.col("facility_type") == "hospital") | text.name_is_hospital(),
        "R3": F.col("n_specialty_categories") >= 5,
        # Counts flagged in R0 aren't trusted for this test.
        "R4": ((beds > 50) & ~F.col("bed_outlier")) | ((doctors > 15) & ~F.col("doctor_outlier")),
        "R5": ~text.lower_name_matches(TRADITIONAL) & ~F.col("flag_name_facilityType"),
    }
    return {step: F.coalesce(condition, F.lit(False)) for step, condition in conditions.items()}


def add_columns(df: DataFrame) -> DataFrame:
    df = df.withColumn("is_veterinary", text.lower_name_matches(VETERINARY))
    failed = F.lit(None).cast("string")
    for step, passed in reversed(steps().items()):
        failed = F.when(~passed, F.lit(step)).otherwise(failed)
    return df.withColumn("large_hospital_step_failed", failed).withColumn(
        "flag_large_hospital", F.col("large_hospital_step_failed").isNull()
    )
