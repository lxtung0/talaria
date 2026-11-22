"""The confidence score and its log (spec #37, "Scoring" and "Log").

Every true rule adds its tier's points to `START`; the worst tier present sets a
cap so positive evidence never covers a real problem. Each step is one line of
`confidence_reasons`, so the log alone replays to the score.

To change a weight, edit `TIERS`. To move a flag to another tier or add one
(the specialty flags from Julia's Reference table go here), edit `RULES`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from pyspark.sql import Column
from pyspark.sql import functions as F

START = 80
MIN_POINTS, MAX_POINTS = 0, 100


@dataclass(frozen=True)
class Tier:
    name: str
    points: int
    cap: int | None  # None: this tier never caps the score.


# Worst first: also the order of the log and of the cap lookup.
TIERS = [
    Tier("critical", -20, 55),
    Tier("major", -10, 75),
    Tier("minor", -3, 90),
    Tier("positive", +10, None),
]
TIER_BY_NAME = {tier.name: tier for tier in TIERS}


@dataclass(frozen=True)
class Rule:
    """`name` is the Silver column it reads, unless `condition` says otherwise."""

    name: str
    tier: str
    reason: str
    condition: Callable[[], Column] | None = field(default=None, compare=False)

    def fired(self) -> Column:
        """Never NULL: a rule whose input is NULL hasn't fired."""
        column = self.condition() if self.condition else F.col(self.name)
        return F.coalesce(column, F.lit(False))

    def line(self) -> str:
        return f"{TIER_BY_NAME[self.tier].points:+d} [{self.tier}] {self.reason}"


# Grouped by tier, in `TIERS` order, so the log reads worst first.
# `flag_specialty_unsupported_by_capability` is deliberately not scored (spec #37).
RULES = [
    # critical: the location or address is wrong, or nothing backs the record.
    Rule("flag_coords_far_from_written_pin", "critical", "The map location is far from the facility's PIN code area"),
    Rule("flag_no_same_prefix_pin_nearby", "critical", "No PIN code from the same region is near the map location"),
    Rule("flag_address_conflict", "critical", "The address names a state that its PIN code and city disagree with"),
    Rule("flag_pin_mismatch", "critical", "The PIN code belongs to a different state than the address"),
    Rule("flag_pin_unverified", "critical", "The PIN code is not in the India Post directory"),
    Rule("no_sources", "critical", "No source pages are listed", lambda: F.col("source_urls").isNull()),
    # major: the record contradicts itself, but the facility likely exists.
    Rule("flag_desc_mentions_other_state", "major", "The description mentions a different state"),
    Rule("flag_coords_shared", "major", "Another facility has exactly the same map location"),
    Rule("flag_affiliation_operator_conflict", "major", "The affiliation and the operator type disagree (government vs private)"),
    Rule("flag_bed_doctor_ratio_outlier", "major", "The number of beds per doctor is unusual for this type of facility"),
    Rule("flag_official_phone_not_in_list", "major", "The official phone is not in the facility's own phone list"),
    Rule("flag_official_website_not_in_list", "major", "The official website is not in the facility's own website list"),
    Rule("flag_only_directory_sources", "major", "All sources are directory or social media listings"),
    # minor: format problems, values already fixed, or an incomplete record.
    Rule("flag_state_corrected", "minor", "The state name was corrected using the PIN code and city"),
    Rule("flag_zero_beds", "minor", "The bed count is listed as zero"),
    Rule("flag_phone_list_without_official", "minor", "Phone numbers are listed but none is marked as official"),
    Rule("flag_single_source_domain", "minor", "All sources come from a single website"),
    Rule("flag_page_update_unparsable", "minor", "The page update date can't be read"),
    Rule("flag_future_page_update", "minor", "The page update date is in the future"),
    Rule("needs_investigation", "minor", "Some lists were cut off at 50 items, so the record may be incomplete"),
    # positive: evidence that raises trust.
    Rule("flag_has_government_source", "positive", "A government website is among the sources"),
    Rule("flag_own_site_in_sources", "positive", "The facility's own website is among the sources"),
]


def rules_in(tier: str) -> list[Rule]:
    return [rule for rule in RULES if rule.tier == tier]


def _any_fired(tier: str) -> Column:
    fired = F.lit(False)
    for rule in rules_in(tier):
        fired = fired | rule.fired()
    return fired


def score_columns() -> dict[str, Column]:
    """`confidence_score` and `confidence_reasons`, as columns over Silver facilities."""
    raw = F.lit(START)
    for rule in RULES:
        raw = raw + F.when(rule.fired(), F.lit(TIER_BY_NAME[rule.tier].points)).otherwise(F.lit(0))

    # The worst tier present names the cap; `when` takes the first match, worst first.
    cap, cap_line = F.lit(None).cast("int"), F.lit(None).cast("string")
    for tier in reversed([tier for tier in TIERS if tier.cap is not None]):
        cap = F.when(_any_fired(tier.name), F.lit(tier.cap)).otherwise(cap)
        cap_line = F.when(_any_fired(tier.name), F.lit(f"cap {tier.cap} [{tier.name}]")).otherwise(cap_line)
    capped = cap.isNotNull() & (raw > cap)

    points = F.when(capped, cap).otherwise(raw)
    points = F.least(F.greatest(points, F.lit(MIN_POINTS)), F.lit(MAX_POINTS))

    lines = [
        F.lit(f"start {START}"),
        *[F.when(rule.fired(), F.lit(rule.line())) for rule in RULES],
        F.when(capped, cap_line),
    ]
    reasons = F.filter(F.array(*lines), lambda line: line.isNotNull())
    return {
        "confidence_score": F.round(points.cast("double") / 100, 2),
        "confidence_reasons": reasons,
    }


def replayed_score(reasons: Column) -> Column:
    """The score the log replays to: start, plus every signed line, cut to the cap line, clamped.

    Used by the runtime checks, so it reads only the log, never the flags.
    """
    start = F.regexp_extract(F.element_at(reasons, 1), r"^start (\d+)$", 1).cast("int")
    deltas = F.filter(reasons, lambda line: line.rlike(r"^[+-]\d+ \["))
    total = F.aggregate(
        deltas,
        F.lit(0),
        lambda acc, line: acc + F.regexp_extract(line, r"^([+-]\d+) ", 1).cast("int"),
    )
    cap_lines = F.filter(reasons, lambda line: line.startswith("cap "))
    cap = F.regexp_extract(F.element_at(cap_lines, 1), r"^cap (\d+) ", 1).cast("int")
    points = start + total
    points = F.when(F.size(cap_lines) > 0, F.least(points, cap)).otherwise(points)
    points = F.least(F.greatest(points, F.lit(MIN_POINTS)), F.lit(MAX_POINTS))
    return F.round(points.cast("double") / 100, 2)
