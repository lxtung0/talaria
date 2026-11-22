"""True / false counts per flag, printed by the Silver facilities notebook (spec #13)."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.silver_facilities import columns

Counts = dict[str, dict[str, int]]


def flag_counts(facilities: DataFrame) -> Counts:
    """`{flag: {"true": n, "false": n}}` for every flag in `columns.NEW_COLUMNS`, in one Spark job."""
    names = [column.name for column in columns.flags()]
    row = facilities.agg(
        *[F.count(F.when(F.col(name), 1)).alias(f"true:{name}") for name in names],
        *[F.count(F.when(~F.col(name), 1)).alias(f"false:{name}") for name in names],
    ).first()
    return {name: {value: row[f"{value}:{name}"] for value in ("true", "false")} for name in names}


def format_flag_counts(counts: Counts) -> str:
    """One line per flag, with its group."""
    groups = {column.name: column.group for column in columns.flags()}
    width = max(len(name) for name in ["flag", *counts])
    lines = [f"group  {'flag':<{width}}  {'true':>8}  {'false':>8}"]
    for name, count in counts.items():
        lines.append(f"{groups[name]:<5}  {name:<{width}}  {count['true']:>8,}  {count['false']:>8,}")
    return "\n".join(lines)
