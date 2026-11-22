"""Facilities per `district_link` value, printed by the notebook (#44)."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.district_link import pipeline


def link_counts(districts: DataFrame) -> dict[str, dict[str, int]]:
    """`{link: {"facilities": n, "approximate": n}}` for every link value, in `pipeline.LINKS` order."""
    rows = districts.groupBy("district_link").agg(
        F.count(F.lit(1)).alias("facilities"), F.count(F.when(F.col("district_approximate"), 1)).alias("approximate")
    ).collect()
    found = {row.district_link: {"facilities": row.facilities, "approximate": row.approximate} for row in rows}
    return {link: found.get(link, {"facilities": 0, "approximate": 0}) for link in pipeline.LINKS}


def format_link_counts(counts: dict[str, dict[str, int]]) -> str:
    total = sum(c["facilities"] for c in counts.values()) or 1
    lines = [f"{'district_link':<20} {'facilities':>10} {'share':>7} {'approximate':>12}"]
    for link, c in counts.items():
        lines.append(f"{link:<20} {c['facilities']:>10,} {c['facilities'] / total:>7.1%} {c['approximate']:>12,}")
    return "\n".join(lines)
