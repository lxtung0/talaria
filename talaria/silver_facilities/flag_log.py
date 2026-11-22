"""Silver facilities flag counts as a long-form DataFrame (pipeline & dashboard friendly).

`flag_counts` in `flag_counts.py` returns nested dicts for the notebook to print;
this module reshapes the same numbers into rows so a pipeline can materialize
them as a table and a dashboard can chart them.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_facilities import columns


def flag_log(facilities: DataFrame) -> DataFrame:
    """One row per flag: `group`, `flag`, `flagged` (true count), in one Spark job."""
    flags = columns.flags()
    row = facilities.agg(*[F.count(F.when(F.col(flag.name), 1)).alias(flag.name) for flag in flags])
    stack_args = ", ".join(f"'{flag.name}', `{flag.name}`" for flag in flags)
    group_map = F.create_map(*[part for flag in flags for part in (F.lit(flag.name), F.lit(flag.group))])
    return row.selectExpr(f"stack({len(flags)}, {stack_args}) AS (flag, flagged)").select(
        group_map[F.col("flag")].alias("group"),
        F.col("flag"),
        F.col("flagged").cast("long").alias("flagged"),
    )
