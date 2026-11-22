"""Silver base per-step counts as a long-form DataFrame (pipeline & dashboard friendly).

`step_counts` in `step_counts.py` returns nested dicts for the notebook to print;
this module reshapes the same numbers into rows so a pipeline can materialize them
as a table and a dashboard can chart them. It reuses the exact same per-step
aggregate columns, so the counts describe exactly what `build_silver_base` does.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.silver_base import columns
from talaria.silver_base.step_counts import (
    _flags,
    _formatting,
    _items_removed,
    _nulls,
    _spelling_fixes,
    _state_check,
)


def step_log(bronze: DataFrame, silver: DataFrame) -> DataFrame:
    """One row per cleaning step: `section`, `label`, `count`.

    - section `rows`: bronze rows, description fragments and exact duplicates
      removed, Silver base rows.
    - sections `nulls`, `items_removed`, `spelling_fixes`, `formatting`,
      `flags`, `state_check`: every other step, zero-count steps dropped.
    """
    facilities = bronze.where(~columns.is_description_fragment()).distinct()

    # Row counts: bronze aggregates joined with the Silver base row count.
    rows = (
        bronze.agg(
            F.count(F.lit(1)).alias("bronze_rows"),
            F.count(F.when(~columns.is_description_fragment(), 1)).alias("real_rows"),
        )
        .crossJoin(silver.agg(F.count(F.lit(1)).alias("silver_base_rows")))
        .selectExpr(
            "'rows' AS section",
            """stack(4,
                'bronze_rows', bronze_rows,
                'description_fragments_removed', bronze_rows - real_rows,
                'exact_duplicates_removed', real_rows - silver_base_rows,
                'silver_base_rows', silver_base_rows
            ) AS (label, count)""",
        )
    )

    # Every other step, in one Spark job over paired bronze/Silver base rows.
    silver_prefixed = silver.select([F.col(f"`{c}`").alias(f"silver.{c}") for c in silver.columns])
    paired = facilities.join(silver_prefixed, facilities["unique_id"] == silver_prefixed["`silver.unique_id`"])

    sections = {
        "nulls": _nulls(facilities),
        "items_removed": _items_removed(),
        "spelling_fixes": _spelling_fixes(),
        "formatting": _formatting(),
        "flags": _flags(),
        "state_check": _state_check(),
    }
    aliases = []
    stack_args = []
    for section, counts in sections.items():
        for label, column in counts.items():
            alias = f"{section}__{label}"
            aliases.append(column.alias(alias))
            stack_args.append(f"'{section}', '{label}', `{alias}`")
    steps = paired.agg(*aliases).selectExpr(
        f"stack({len(stack_args)}, {', '.join(stack_args)}) AS (section, label, count)"
    )

    return rows.unionByName(
        steps.select(
            F.col("section"),
            F.col("label"),
            F.col("count").cast("long").alias("count"),
        ).where(F.col("count") > 0)
    )

