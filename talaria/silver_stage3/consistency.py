"""Step 5, C1-C5: whether procedure, equipment and capability back each other and the
specialties (#35). Needs steps 1 and 4.

Veterinary Facilities are checked like any other: #35 leaves them out of the large
hospital funnel (R2-R5), and its expected C counts include them."""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_stage3 import text
from talaria.silver_stage3.references import References

# Working columns, dropped by the pipeline's final select.
_ITEMS = {field: f"_{field}_items" for field in text.TEXT_FIELDS}  # non-blank items
_CLEAN = {field: f"_{field}_clean" for field in text.TEXT_FIELDS}  # ... without NOISE items
_FOUND = {field: f"_{field}_categories" for field in text.TEXT_FIELDS}  # text_categories(field)


def _empty(field: str) -> Column:
    return F.size(_ITEMS[field]) == 0


def _matches(field: str, pattern: str) -> Column:
    return text.any_item_matches(F.col(_CLEAN[field]), pattern)


def add_columns(df: DataFrame, references: References) -> DataFrame:
    for field in text.TEXT_FIELDS:
        df = df.withColumn(_ITEMS[field], text.items(F.col(field)))
        df = df.withColumn(_CLEAN[field], text.without_noise(F.col(_ITEMS[field])))
        df = df.withColumn(_FOUND[field], text.text_categories(F.col(_CLEAN[field]), references))
    df = _unverified(df)
    df = _partial(df, references)
    df = _specialty_unsupported(df, references)
    df = _major_orphan(df, references)
    return _merge_different(df, references)


def _unverified(df: DataFrame) -> DataFrame:
    """C1: procedure, equipment or capability is empty."""
    reason = F.concat_ws(", ", *[F.when(_empty(field), F.lit(field)) for field in text.TEXT_FIELDS])
    return df.withColumn("unverified_reason", F.when(reason != "", reason)).withColumn(
        "flag_unverified", F.col("unverified_reason").isNotNull()
    )


def _partial(df: DataFrame, references: References) -> DataFrame:
    """C2: a procedure without the equipment it needs, or equipment without its procedure."""
    forward, reverse = [], []
    for rule in references.procedure_equipment_rules:
        service = F.lit(rule.service)
        if rule.check_forward:
            gap = _matches("procedure", rule.procedure_regex) & ~_matches("equipment", rule.equipment_regex)
            forward.append(F.when(gap, service))
        if rule.check_reverse:
            gap = (
                _matches("equipment", rule.equipment_regex)
                & ~_matches("procedure", rule.procedure_regex)
                & ~_matches("capability", rule.procedure_regex)
            )
            reverse.append(F.when(gap, service))

    def part(label: str, services: list[Column]) -> Column:
        found = F.array_compact(F.array(*services)) if services else text.empty()
        return F.when(F.size(found) > 0, F.concat(F.lit(f"{label}: "), F.array_join(found, ", ")))

    reason = F.concat_ws(
        " | ", part("procedure without equipment", forward), part("equipment without procedure", reverse)
    )
    checked = ~_empty("procedure") & ~_empty("equipment")
    return df.withColumn("partial_reason", F.when(checked & (reason != ""), reason)).withColumn(
        "flag_partial", F.col("partial_reason").isNotNull()
    )


def _specialty_unsupported(df: DataFrame, references: References) -> DataFrame:
    """C3: at least half the core specialty categories (all of them for a large hospital)
    are named by none of procedure, equipment and capability."""
    found = F.array_distinct(F.concat(*[F.col(_FOUND[field]) for field in text.TEXT_FIELDS]))
    core = F.col("core_categories")
    any_text = F.lit(False)
    for field in text.TEXT_FIELDS:
        any_text = any_text | ~_empty(field)
    checked = (F.size(core) > 0) & any_text
    missing = F.filter(core, lambda category: ~text.supported(category, found, references))
    df = df.withColumn("unsupported_specialties", F.when(checked, missing)).withColumn(
        "unsupported_specialty_share",
        F.when(checked, F.size("unsupported_specialties") / F.size(core)),
    )
    share, large = F.col("unsupported_specialty_share"), F.col("flag_large_hospital")
    flag = ((share >= 0.5) & ~large) | ((share == 1.0) & large)
    return df.withColumn("flag_specialty_unsupported", F.coalesce(flag, F.lit(False)))


def _major_orphan(df: DataFrame, references: References) -> DataFrame:
    """C4: a high-risk service named in the text with no specialty to back it. Not for large hospitals."""
    specialties = F.col("specialty_categories")

    def labelled(label: str, hits: list[Column]) -> Column:
        found = F.array_compact(F.array(*hits)) if hits else text.empty()
        return F.when(F.size(found) > 0, F.concat(F.lit(f"{label}: "), F.array_join(found, ", ")))

    parts = []
    for field in ["procedure", "equipment"]:
        hits = [
            F.when(
                F.array_contains(_FOUND[field], category)
                & ~F.array_contains(specialties, category)
                & ~F.arrays_overlap(specialties, text.literal_array(accepted)),
                F.lit(category),
            )
            for category, accepted in references.high_risk_categories.items()
        ]
        parts.append(labelled(field, hits))
    units = [
        F.when(
            _matches("capability", regex) & ~F.arrays_overlap(specialties, text.literal_array(supporting)),
            F.lit(unit),
        )
        for unit, (regex, supporting) in references.capability_units.items()
    ]
    parts.append(labelled("capability unit", units))

    reason = F.concat_ws("; ", *parts)
    checked = ~F.col("flag_large_hospital")
    return df.withColumn("orphan_reason", F.when(checked & (reason != ""), reason)).withColumn(
        "flag_major_orphan", F.col("orphan_reason").isNotNull()
    )


def _merge_different(df: DataFrame, references: References) -> DataFrame:
    """C5: the procedures (and capability, when there is one) name specific categories,
    none of which backs a core specialty: the text may describe a different Facility."""
    core = F.col("core_categories")
    generic = text.literal_array(text.GENERIC)

    def different(field: str) -> Column:
        found = F.col(_FOUND[field])
        return (F.size(F.array_except(found, generic)) > 0) & ~F.exists(
            core, lambda category: text.supported(category, found, references)
        )

    flag = (
        (F.size(core) > 0)
        & ~_empty("procedure")
        & different("procedure")
        & (_empty("capability") | different("capability"))
    )
    return df.withColumn("flag_merge_different", F.coalesce(flag, F.lit(False)))
