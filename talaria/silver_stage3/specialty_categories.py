"""Step 1: the categories of a Facility's specialty codes (#35)."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.silver_stage3 import text
from talaria.silver_stage3.references import References


def add_columns(df: DataFrame, references: References) -> DataFrame:
    """Each code is looked up exactly; an unknown code is `Other / Unclassified`."""
    mapping = text.literal_map(references.specialty_categories, "string")
    categories = F.array_sort(
        F.array_distinct(
            F.transform(
                text.items(F.col("specialties")),
                lambda code: F.coalesce(F.try_element_at(mapping, code), F.lit(text.OTHER)),
            )
        )
    )
    df = df.withColumn("specialty_categories", categories)
    counted = F.filter("specialty_categories", lambda c: ~c.isin(text.GENERAL_MEDICINE, text.OTHER))
    return df.withColumn("n_specialty_categories", F.size(counted)).withColumn(
        "core_categories", F.filter("specialty_categories", lambda c: ~c.isin(*text.GENERIC))
    )
