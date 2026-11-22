"""Gold runtime checks (spec #37, "Runtime checks").

Run by the Gold notebook on live data, before anything is written.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.gold import columns, scoring
from talaria.silver_base.checks import unique_id_counts, unique_id_failures


def check_gold(silver: DataFrame, facilities: DataFrame, items: DataFrame) -> None:
    """Raise ValueError naming every failed check; return quietly when all pass.

    Compares against the in-scope Silver rows: veterinary facilities are left out of Gold.
    """
    silver = columns.in_scope(silver)
    failures = _schema_failures("gold_facilities", facilities, columns.GOLD_FACILITIES)
    failures += _schema_failures("gold_facility_items", items, columns.GOLD_FACILITY_ITEMS)
    if failures:
        _fail(failures)  # The value checks need every column with its type.
    failures = _facility_failures(silver, facilities)
    failures += _copied_value_failures(silver, facilities)
    failures += _item_failures(silver, facilities, items)
    failures += _citation_failures(facilities, items)
    if failures:
        _fail(failures)


def _fail(failures: list[str]) -> None:
    raise ValueError("Gold runtime checks failed:\n- " + "\n- ".join(failures))


def _schema_failures(table: str, df: DataFrame, expected: dict[str, str]) -> list[str]:
    actual = dict(df.dtypes)
    failures = []
    for name, kind in expected.items():
        if name not in actual:
            failures.append(f"{table}.{name}: column is missing")
        elif actual[name] != kind:
            failures.append(f"{table}.{name}: type is {actual[name]}, expected {kind}")
    failures += [f"{table}.{name}: unexpected column" for name in actual if name not in expected]
    return failures


def _location_uncertain() -> Column:
    any_flag = F.lit(False)
    for name in columns.LOCATION_FLAGS:
        any_flag = any_flag | F.col(name)
    return any_flag


def _facility_failures(silver: DataFrame, facilities: DataFrame) -> list[str]:
    score, reasons = F.col("confidence_score"), F.col("confidence_reasons")
    counts = facilities.agg(
        *unique_id_counts(),
        F.count(F.when(score.isNull() | (score < 0) | (score > 1), 1)).alias("bad_score"),
        F.count(F.when(reasons.isNull(), 1)).alias("null_reasons"),
        F.count(F.when(scoring.replayed_score(reasons) != score, 1)).alias("replay_mismatch"),
        F.count(F.when(F.col("location_uncertain").isNull(), 1)).alias("null_location"),
    ).first()
    failures = unique_id_failures(counts)
    silver_rows = silver.count()
    if counts.rows != silver_rows:
        failures.append(f"gold_facilities has {counts.rows} rows, Silver Stage 3 has {silver_rows}")
    if counts.bad_score:
        failures.append(f"confidence_score: {counts.bad_score} row(s) NULL or outside 0-1")
    if counts.null_reasons:
        failures.append(f"confidence_reasons: {counts.null_reasons} row(s) NULL")
    if counts.replay_mismatch:
        failures.append(f"confidence_reasons: {counts.replay_mismatch} row(s) don't replay to confidence_score")
    if counts.null_location:
        failures.append(f"location_uncertain: {counts.null_location} row(s) NULL")

    wrong_location = (
        silver.select("unique_id", _location_uncertain().alias("expected"))
        .join(facilities.select("unique_id", "location_uncertain"), "unique_id")
        .where(F.col("expected") != F.col("location_uncertain"))
        .count()
    )
    if wrong_location:
        failures.append(f"location_uncertain: {wrong_location} row(s) differ from the group H flags")
    return failures


def _copied_value_failures(silver: DataFrame, facilities: DataFrame) -> list[str]:
    """Each copied column's hash in Silver and in Gold, compared per Facility."""
    names = [name for name in [*columns.COPIED_COLUMNS, "needs_investigation"] if name != "unique_id"]

    def hashed(df: DataFrame, side: str) -> DataFrame:
        return df.select(F.col("unique_id").alias(f"{side}:id"), *[_value_hash(n).alias(f"{side}:{n}") for n in names])

    before, after = hashed(silver, "silver"), hashed(facilities, "gold")
    silver_id, gold_id = F.col("silver:id"), F.col("gold:id")
    matched = silver_id.isNotNull() & gold_id.isNotNull()
    counts = (
        before.join(after, silver_id == gold_id, "full")
        .agg(
            F.count(F.when(gold_id.isNull(), 1)).alias("lost"),
            F.count(F.when(silver_id.isNull(), 1)).alias("added"),
            *[F.count(F.when(matched & (F.col(f"silver:{n}") != F.col(f"gold:{n}")), 1)).alias(n) for n in names],
        )
        .first()
    )
    failures = [f"{n}: {counts[n]} row(s) differ from Silver" for n in names if counts[n]]
    if counts["lost"] or counts["added"]:
        failures.append(f"unique_id differs from Silver: {counts['lost']} lost, {counts['added']} added")
    return failures


def _value_hash(name: str) -> Column:
    """A never-NULL hash that tells NULL, an empty list and a list holding NULL apart."""
    return F.sha2(F.to_json(F.struct(F.col(name))), 256)


def _citation_failures(facilities: DataFrame, items: DataFrame) -> list[str]:
    """Every citation has text, and every cited `item_id` is a row of `gold_facility_items`."""
    cited = facilities.select(F.explode("confidence_citations").alias("c")).select("c.*")
    blank = cited.where(F.col("text").isNull()).count()
    unknown = cited.where(F.col("item_id").isNotNull()).join(items, "item_id", "left_anti").count()
    failures = []
    if blank:
        failures.append(f"confidence_citations: {blank} citation(s) without text")
    if unknown:
        failures.append(f"confidence_citations: {unknown} citation(s) whose item_id isn't in gold_facility_items")
    return failures


def _list_length(name: str) -> Column:
    return F.when(F.col(name).isNull(), 0).otherwise(F.size(name))


def _item_failures(silver: DataFrame, facilities: DataFrame, items: DataFrame) -> list[str]:
    counts = items.agg(
        F.count(F.lit(1)).alias("rows"),
        F.count("item_id").alias("non_null_ids"),
        F.countDistinct("item_id").alias("distinct_ids"),
        F.count(F.when(~F.col("item_type").isin(columns.ITEM_TYPES) | F.col("item_type").isNull(), 1)).alias("bad_type"),
        F.count(F.when(F.col("item_text").isNull(), 1)).alias("null_text"),
    ).first()
    failures = []
    if counts.non_null_ids != counts.rows:
        failures.append(f"item_id is null in {counts.rows - counts.non_null_ids} row(s)")
    if counts.distinct_ids != counts.non_null_ids:
        failures.append(f"item_id is repeated: {counts.non_null_ids - counts.distinct_ids} extra row(s)")
    if counts.bad_type:
        failures.append(f"item_type: {counts.bad_type} row(s) not one of {columns.ITEM_TYPES}")
    if counts.null_text:
        failures.append(f"item_text: {counts.null_text} row(s) NULL")

    orphans = items.join(facilities, "unique_id", "left_anti").count()
    if orphans:
        failures.append(f"gold_facility_items: {orphans} row(s) whose unique_id isn't in gold_facilities")

    per_facility = items.groupBy("unique_id").agg(
        *[F.count(F.when(F.col("item_type") == t, 1)).alias(t) for t in columns.LIST_ITEM_TYPES.values()]
    )
    expected = silver.select(
        "unique_id", *[_list_length(name).alias(f"expected:{t}") for name, t in columns.LIST_ITEM_TYPES.items()]
    )
    compared = expected.join(per_facility, "unique_id", "left").agg(
        *[
            F.count(F.when(F.col(f"expected:{t}") != F.coalesce(F.col(t), F.lit(0)), 1)).alias(t)
            for t in columns.LIST_ITEM_TYPES.values()
        ]
    ).first()
    for name, t in columns.LIST_ITEM_TYPES.items():
        if compared[t]:
            failures.append(f"{t} items: {compared[t]} Facilities whose item count differs from the length of {name}")
    return failures
