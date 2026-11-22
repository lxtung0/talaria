"""The Silver Stage 3 pipeline: one step per section of #35.

To add a rule: write it in its step's module, list its columns in
`columns.NEW_COLUMNS`, and add it to `rule_counts.RULES`.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from talaria.silver_stage3 import capacity, columns, consistency, large_hospital, name_type, specialty_categories, text
from talaria.silver_stage3.references import References, load_references

LIST_COLUMNS = ["specialties", *text.TEXT_FIELDS]
COUNT_COLUMNS = ["bed_count", "number_doctors"]


def build_silver_stage3(silver_facilities: DataFrame, references: References | None = None) -> DataFrame:
    """Silver facilities minus `columns.REPLACED_COLUMNS`, every other column unchanged,
    plus `columns.NEW_COLUMNS`. `references` defaults to the CSVs in the repo.

    Raises ValueError if a new column name is already in the input.
    """
    references = references or load_references()
    clashes = [column.name for column in columns.NEW_COLUMNS if column.name in silver_facilities.columns]
    if clashes:
        raise ValueError(f"Silver Stage 3 columns already in the input: {', '.join(clashes)}")
    kept = [name for name in silver_facilities.columns if name not in columns.REPLACED_COLUMNS]

    # The rules read typed copies; the input columns themselves are never overwritten.
    df = silver_facilities
    originals = {name: f"_original_{name}" for name in [*LIST_COLUMNS, *COUNT_COLUMNS]}
    for name, original in originals.items():
        df = df.withColumn(original, F.col(name))
    df = _typed(df)

    df = specialty_categories.add_columns(df, references)
    df = capacity.add_columns(df)
    df = name_type.add_columns(df)
    df = large_hospital.add_columns(df)
    df = consistency.add_columns(df, references)
    # Only listed columns leave the function, so working columns are never stored.
    return df.select(
        *[F.col(originals[name]).alias(name) if name in originals else F.col(name) for name in kept],
        *[column.name for column in columns.NEW_COLUMNS],
    )


def _typed(df: DataFrame) -> DataFrame:
    """List columns as `array<string>` (JSON-array text is parsed), counts as int."""
    types = dict(df.dtypes)
    for name in LIST_COLUMNS:
        if types[name] == "string":
            df = df.withColumn(name, F.from_json(name, T.ArrayType(T.StringType())))
    for name in COUNT_COLUMNS:
        df = df.withColumn(name, F.col(name).cast("int"))
    return df
