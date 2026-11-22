"""Score distribution and per-rule fire counts, printed by the Gold notebook (spec #37)."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.gold import scoring


def score_counts(silver_facilities: DataFrame, facilities: DataFrame) -> dict:
    """`{"rules": {rule: n}, "worst_tier": {tier: n}, "scores": {score: n}}`, read from Silver flags and Gold scores."""
    fired = silver_facilities.agg(
        *[F.count(F.when(rule.fired(), 1)).alias(rule.name) for rule in scoring.RULES]
    ).first()

    worst = F.lit("none")
    for tier in reversed([t for t in scoring.TIERS if t.cap is not None]):
        any_fired = F.lit(False)
        for rule in scoring.rules_in(tier.name):
            any_fired = any_fired | rule.fired()
        worst = F.when(any_fired, F.lit(tier.name)).otherwise(worst)
    tiers = {row.tier: row["count"] for row in silver_facilities.groupBy(worst.alias("tier")).count().collect()}

    scores = {row.confidence_score: row["count"] for row in facilities.groupBy("confidence_score").count().collect()}
    return {
        "rules": {rule.name: fired[rule.name] for rule in scoring.RULES},
        "worst_tier": {name: tiers.get(name, 0) for name in [*[t.name for t in scoring.TIERS if t.cap], "none"]},
        "scores": dict(sorted(scores.items())),
    }


def format_score_counts(counts: dict) -> str:
    tier_of = {rule.name: rule.tier for rule in scoring.RULES}
    width = max(len(name) for name in counts["rules"])
    lines = [f"{'tier':<9} {'rule':<{width}} {'fired':>7}"]
    lines += [f"{tier_of[name]:<9} {name:<{width}} {n:>7,}" for name, n in counts["rules"].items()]
    lines += ["", "Worst tier per Facility:"]
    lines += [f"  {name:<9} {n:>7,}" for name, n in counts["worst_tier"].items()]
    lines += ["", "confidence_score distribution:"]
    lines += [f"  {score:.2f} {n:>7,}" for score, n in counts["scores"].items()]
    return "\n".join(lines)
