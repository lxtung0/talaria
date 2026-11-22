"""Silver base runtime checks (spec #1, "Runtime checks").

Run by the Silver base notebook against the live output of `build_silver_base`,
to catch surprises in the real data that the unit-test fixtures didn't anticipate.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from talaria.silver_base.text import null_if_missing


def check_silver_base(silver: DataFrame) -> None:
    """Raise ValueError naming every failed check; return quietly when all pass.

    - `unique_id` is unique and non-null.
    - No text column holds a Missing-value spelling (`null`, `""`, `[]`, the hidden-email placeholder).
    - No list column holds an empty array, or an empty item (NULL or a Missing-value spelling).
    """
    text_columns = [f.name for f in silver.schema.fields if isinstance(f.dataType, T.StringType)]
    list_columns = [f.name for f in silver.schema.fields if isinstance(f.dataType, T.ArrayType)]

    counts = silver.agg(
        F.count(F.lit(1)).alias("rows"),
        F.count("unique_id").alias("non_null_ids"),
        F.countDistinct("unique_id").alias("distinct_ids"),
        *[F.count(F.when(_is_missing_spelling(F.col(n)), 1)).alias(f"missing:{n}") for n in text_columns],
        *[
            F.count(F.when(F.exists(F.col(n), lambda item: item.isNull() | _is_missing_spelling(item)), 1)).alias(
                f"empty_item:{n}"
            )
            for n in list_columns
        ],
        *[F.count(F.when(F.size(F.col(n)) == 0, 1)).alias(f"empty_list:{n}") for n in list_columns],
    ).first()

    failures = []
    if counts.non_null_ids != counts.rows:
        failures.append(f"unique_id is null in {counts.rows - counts.non_null_ids} row(s)")
    if counts.distinct_ids != counts.non_null_ids:
        failures.append(f"unique_id is repeated: {counts.non_null_ids} ids but {counts.distinct_ids} distinct")
    for n in text_columns:
        if counts[f"missing:{n}"]:
            failures.append(f"{n}: {counts[f'missing:{n}']} row(s) with a Missing-value spelling")
    for n in list_columns:
        if counts[f"empty_item:{n}"]:
            failures.append(f"{n}: {counts[f'empty_item:{n}']} row(s) with an empty list item")
        if counts[f"empty_list:{n}"]:
            failures.append(f"{n}: {counts[f'empty_list:{n}']} row(s) with an empty list")
    if failures:
        raise ValueError("Silver base runtime checks failed:\n- " + "\n- ".join(failures))


def _is_missing_spelling(col: Column) -> Column:
    """True for a non-NULL value that the Missing-value rule would turn into NULL."""
    return col.isNotNull() & null_if_missing(col).isNull()
