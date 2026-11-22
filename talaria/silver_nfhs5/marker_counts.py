"""How many districts carry each NFHS-5 marker, per indicator, printed by the notebook (#41)."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.silver_nfhs5 import columns


def marker_counts(silver: DataFrame) -> dict[str, dict[str, int]]:
    """`{indicator: {"suppressed": n, "low_sample": n}}` for indicators with any marker, most suppressed first."""
    counts = {}
    for marker, column in [("suppressed", columns.SUPPRESSED), ("low_sample", columns.LOW_SAMPLE)]:
        for row in silver.select(F.explode(column).alias("name")).groupBy("name").count().collect():
            counts.setdefault(row["name"], {"suppressed": 0, "low_sample": 0})[marker] = row["count"]
    return dict(sorted(counts.items(), key=lambda item: (-item[1]["suppressed"], -item[1]["low_sample"], item[0])))


def format_marker_counts(counts: dict[str, dict[str, int]]) -> str:
    width = max([len("indicator"), *map(len, counts)])
    lines = [f"{'indicator':<{width}}  {'*':>5}  {'(x)':>5}"]
    lines += [f"{name:<{width}}  {c['suppressed']:>5}  {c['low_sample']:>5}" for name, c in counts.items()]
    return "\n".join(lines)
