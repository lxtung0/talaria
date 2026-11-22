"""Silver facilities runtime checks (spec #13, "Runtime checks").

Run by the Silver facilities notebook on live data, before anything is written.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_base.checks import unique_id_counts, unique_id_failures
from talaria.silver_facilities import columns, location


def check_silver_facilities(silver_base: DataFrame, facilities: DataFrame) -> None:
    """Raise ValueError naming every failed check; return quietly when all pass.

    - The columns are Silver base's, same types, plus exactly `columns.NEW_COLUMNS`.
    - Row count equals Silver base; `unique_id` is unique and non-null.
    - Every Silver base value is unchanged.
    - No flag is NULL.
    - `primary_affiliation` is NULL exactly when `affiliation_types` is NULL.
    - Group H (location) flags are false for every Facility without a Silver base location flag.
    """
    failures = _schema_failures(silver_base, facilities)
    if failures:
        # The value checks need every column to be there with its type.
        _fail(failures)

    flags = [column.name for column in columns.flags()]
    counts = facilities.agg(
        *unique_id_counts(),
        *[F.count(F.when(F.col(name).isNull(), 1)).alias(f"null:{name}") for name in flags],
        *_primary_affiliation_counts(),
        *[F.count(F.when(F.col(name) & ~_has_location_flag(), 1)).alias(f"out_of_scope:{name}") for name in location.FLAGS],
    ).first()

    failures = unique_id_failures(counts)
    base_rows = silver_base.count()
    if counts.rows != base_rows:
        failures.append(f"row count is {counts.rows}, Silver base has {base_rows}")
    for name in flags:
        if counts[f"null:{name}"]:
            failures.append(f"{name}: {counts[f'null:{name}']} row(s) with a NULL flag")
    failures += _primary_affiliation_failures(counts)
    for name in location.FLAGS:
        if counts[f"out_of_scope:{name}"]:
            failures.append(f"{name}: true for {counts[f'out_of_scope:{name}']} row(s) without a Silver base location flag")
    failures += _changed_value_failures(silver_base, facilities)
    if failures:
        _fail(failures)


def _has_location_flag() -> Column:
    has_flag = F.lit(False)
    for name in location.SILVER_BASE_LOCATION_FLAGS:
        has_flag = has_flag | F.col(name)
    return has_flag


def _fail(failures: list[str]) -> None:
    raise ValueError("Silver facilities runtime checks failed:\n- " + "\n- ".join(failures))


def _primary_affiliation_counts() -> list[Column]:
    primary, affiliations = F.col("primary_affiliation"), F.col("affiliation_types")
    return [
        F.count(F.when(primary.isNull() & affiliations.isNotNull(), 1)).alias("primary_missing"),
        F.count(F.when(primary.isNotNull() & affiliations.isNull(), 1)).alias("primary_unexpected"),
    ]


def _primary_affiliation_failures(counts) -> list[str]:
    failures = []
    if counts.primary_missing:
        failures.append(f"primary_affiliation: {counts.primary_missing} row(s) NULL while affiliation_types isn't")
    if counts.primary_unexpected:
        failures.append(f"primary_affiliation: {counts.primary_unexpected} row(s) set while affiliation_types is NULL")
    return failures


def _schema_failures(silver_base: DataFrame, facilities: DataFrame) -> list[str]:
    expected = dict(silver_base.dtypes) | {column.name: column.type for column in columns.NEW_COLUMNS}
    actual = dict(facilities.dtypes)
    failures = []
    for name, kind in expected.items():
        if name not in actual:
            failures.append(f"{name}: column is missing")
        elif actual[name] != kind:
            failures.append(f"{name}: type is {actual[name]}, expected {kind}")
    failures += [f"{name}: unexpected column" for name in actual if name not in expected]
    return failures


def _changed_value_failures(silver_base: DataFrame, facilities: DataFrame) -> list[str]:
    """Each column's hash before and after, compared per Facility."""
    names = [name for name in silver_base.columns if name != "unique_id"]

    def hashed(df: DataFrame, side: str) -> DataFrame:
        return df.select(
            F.col("unique_id").alias(f"{side}:id"),
            *[_value_hash(name).alias(f"{side}:{name}") for name in names],
        )

    before, after = hashed(silver_base, "before"), hashed(facilities, "after")
    before_id, after_id = F.col("before:id"), F.col("after:id")
    matched = before_id.isNotNull() & after_id.isNotNull()
    counts = (
        before.join(after, before_id == after_id, "full")
        .agg(
            F.count(F.when(after_id.isNull(), 1)).alias("lost"),
            F.count(F.when(before_id.isNull(), 1)).alias("added"),
            *[
                F.count(F.when(matched & (F.col(f"before:{name}") != F.col(f"after:{name}")), 1)).alias(name)
                for name in names
            ],
        )
        .first()
    )
    failures = [f"{name}: {counts[name]} row(s) changed from Silver base" for name in names if counts[name]]
    if counts["lost"] or counts["added"]:
        failures.append(f"unique_id differs from Silver base: {counts['lost']} lost, {counts['added']} added")
    return failures


def _value_hash(name: str) -> Column:
    """A never-NULL hash that differs for NULL, an empty list and a list holding NULL.

    Not `xxhash64`, which skips NULLs and so hashes all three alike. The timestamp
    format is spelled out because `to_json` otherwise drops microseconds.
    """
    as_json = F.to_json(F.struct(F.col(name)), {"timestampFormat": "yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXX"})
    return F.sha2(as_json, 256)
