"""Step 2, R0: capacity outliers (#35). Flags only; `bed_count` and `number_doctors` are kept."""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_stage3 import text

BED_RULES = ["R0-1", "R0-6"]
DOCTOR_RULES = ["R0-2", "R0-3", "R0-4", "R0-5"]


def rules() -> dict[str, Column]:
    """Each R0 rule by id; never NULL (a NULL count fails the rule)."""
    beds, doctors = F.col("bed_count"), F.col("number_doctors")
    hospital = F.col("facility_type") == "hospital"
    conditions = {
        "R0-1": beds > 4000,
        "R0-2": doctors > 2 * beds,
        "R0-3": (text.clinic_type() | (text.name_is_clinic() & ~text.name_is_hospital())) & (doctors >= 150),
        "R0-4": (beds > 0) & (doctors <= beds / 100),
        "R0-5": hospital & (doctors == 1),
        "R0-6": hospital & beds.between(1, 5),
    }
    return {rule: F.coalesce(condition, F.lit(False)) for rule, condition in conditions.items()}


def add_columns(df: DataFrame) -> DataFrame:
    fired = rules()
    reason = F.concat_ws("; ", *[F.when(condition, F.lit(rule)) for rule, condition in fired.items()])

    def any_of(ids: list[str]) -> Column:
        result = F.lit(False)
        for rule in ids:
            result = result | fired[rule]
        return result

    return (
        df.withColumn("flag_facility_capacity_outlier", any_of(list(fired)))
        .withColumn("outlier_reason", F.when(reason != "", reason))
        .withColumn("bed_outlier", any_of(BED_RULES))
        .withColumn("doctor_outlier", any_of(DOCTOR_RULES))
    )
