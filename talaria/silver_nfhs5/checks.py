"""Silver NFHS-5 runtime checks (#41). Run by the notebook on live data, before anything is written."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.silver_base.aliases import OFFICIAL_STATES
from talaria.silver_nfhs5 import columns, pipeline


def check_silver_nfhs5(bronze: DataFrame, silver: DataFrame) -> None:
    """Raise ValueError naming every failed check; return quietly when all pass.

    - The columns are bronze's, then `columns.NEW_COLUMNS`.
    - Row count equals bronze; `(state_ut, district_name)` is unique and non-null.
    - Every state is an official name; every survey size is non-null.
    - An indicator is NULL only when it is suppressed (`*`) or its source value is NULL or blank.
    """
    expected = [*bronze.columns, *columns.NEW_COLUMNS]
    if silver.columns != expected:
        _fail([f"columns are {silver.columns}, expected {expected}"])

    indicators = columns.indicators(bronze.columns)
    state, district = F.col(columns.STATE), F.col(columns.DISTRICT)
    counts = silver.agg(
        F.count(F.lit(1)).alias("rows"),
        F.count(F.when(state.isNull() | district.isNull(), 1)).alias("null_key"),
        F.countDistinct(state, district).alias("distinct_keys"),
        F.count(F.when(state.isNotNull() & ~state.isin(OFFICIAL_STATES), 1)).alias("unofficial_state"),
        *[F.count(F.when(F.col(n).isNull(), 1)).alias(f"null:{n}") for n in columns.SURVEY_SIZES],
    ).first()

    failures = []
    bronze_rows = bronze.count()
    if counts.rows != bronze_rows:
        failures.append(f"row count is {counts.rows}, bronze has {bronze_rows}")
    if counts.null_key:
        failures.append(f"{columns.STATE}/{columns.DISTRICT}: {counts.null_key} row(s) NULL (state not recognised?)")
    if counts.distinct_keys != counts.rows - counts.null_key:
        failures.append(f"({columns.STATE}, {columns.DISTRICT}) is repeated: {counts.distinct_keys} distinct")
    if counts.unofficial_state:
        failures.append(f"{columns.STATE}: {counts.unofficial_state} row(s) not an official state name")
    failures += [f"{n}: {counts[f'null:{n}']} row(s) NULL" for n in columns.SURVEY_SIZES if counts[f"null:{n}"]]
    failures += _unparsed_failures(bronze, silver, indicators)
    if failures:
        _fail(failures)


def _unparsed_failures(bronze: DataFrame, silver: DataFrame, indicators: list[str]) -> list[str]:
    """Indicators NULL in Silver although bronze had a non-blank, non-`*` value, matched per district."""
    key = [columns.STATE, columns.DISTRICT]
    raw = bronze.select(
        pipeline.state(F.col(columns.STATE)).alias(columns.STATE),
        pipeline.district(F.col(columns.DISTRICT)).alias(columns.DISTRICT),
        *[pipeline.trimmed(n).alias(f"raw:{n}") for n in indicators],
    )
    joined = raw.join(silver.select(*key, *indicators), key)
    counts = joined.agg(
        *[
            F.count(F.when(F.col(n).isNull() & F.col(f"raw:{n}").isNotNull() & (F.col(f"raw:{n}") != "*"), 1)).alias(n)
            for n in indicators
        ]
    ).first()
    return [f"{n}: {counts[n]} value(s) that aren't a number, `*` or `(number)`" for n in indicators if counts[n]]


def _fail(failures: list[str]) -> None:
    raise ValueError("Silver NFHS-5 runtime checks failed:\n- " + "\n- ".join(failures))
