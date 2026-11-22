"""Step 3, F1: a name that contradicts the facility type (#35)."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.silver_stage3 import text


def add_columns(df: DataFrame) -> DataFrame:
    hospital_name, clinic_name = text.name_is_hospital(), text.name_is_clinic()
    # "Dental Hospital" is a normal name for a dental clinic in India.
    dental = text.lower_name_matches("dental")
    conflict = (hospital_name & ~clinic_name & text.clinic_type() & ~dental) | (
        clinic_name & ~hospital_name & F.coalesce(F.col("facility_type") == "hospital", F.lit(False))
    )
    return df.withColumn("flag_name_facilityType", conflict)
