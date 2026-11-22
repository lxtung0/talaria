"""Silver Stage 3 runtime checks (#35). Run by the notebook on live data, before anything is written."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.silver_base.checks import unique_id_counts, unique_id_failures
from talaria.silver_facilities.checks import changed_value_failures
from talaria.silver_stage3 import columns


def check_silver_stage3(silver_facilities: DataFrame, stage3: DataFrame) -> None:
    """Raise ValueError naming every failed check; return quietly when all pass.

    - The columns are Silver facilities' minus `columns.REPLACED_COLUMNS`, same types,
      plus exactly `columns.NEW_COLUMNS`.
    - Row count equals Silver facilities; `unique_id` is unique and non-null.
    - Every kept Silver facilities value is unchanged.
    - No flag is NULL.
    - Every true C2-C5 flag has evidence in `evidence_items`, and every evidence item
      belongs to a true flag.
    """
    kept = [name for name in silver_facilities.columns if name not in columns.REPLACED_COLUMNS]
    failures = _schema_failures(silver_facilities, stage3, kept)
    if failures:
        _fail(failures)

    flags = [column.name for column in columns.flags()]
    counts = stage3.agg(
        *unique_id_counts(),
        *[F.count(F.when(F.col(name).isNull(), 1)).alias(f"null:{name}") for name in flags],
        *_evidence_counts(),
    ).first()
    failures = unique_id_failures(counts)
    input_rows = silver_facilities.count()
    if counts.rows != input_rows:
        failures.append(f"row count is {counts.rows}, Silver facilities has {input_rows}")
    failures += [
        f"{name}: {counts[f'null:{name}']} row(s) with a NULL flag" for name in flags if counts[f"null:{name}"]
    ]
    failures += _evidence_failures(counts)
    failures += changed_value_failures(silver_facilities, stage3, kept, "Silver facilities")
    if failures:
        _fail(failures)


# The rules `evidence_items` cites, by their flag.
EVIDENCE_FLAGS = {
    "C2": "flag_partial",
    "C3": "flag_specialty_unsupported",
    "C4": "flag_major_orphan",
    "C5": "flag_merge_different",
}


def _evidence_counts() -> list:
    evidence = F.coalesce(F.col("evidence_items"), F.array())
    counts = []
    for rule, flag in EVIDENCE_FLAGS.items():
        cited = F.exists(evidence, lambda item: item["rule"] == rule)
        counts.append(F.count(F.when(F.col(flag) & ~cited, 1)).alias(f"uncited:{rule}"))
        counts.append(F.count(F.when(~F.col(flag) & cited, 1)).alias(f"unflagged:{rule}"))
    return counts


def _evidence_failures(counts) -> list[str]:
    failures = []
    for rule, flag in EVIDENCE_FLAGS.items():
        if counts[f"uncited:{rule}"]:
            failures.append(f"evidence_items: {counts[f'uncited:{rule}']} row(s) with {flag} but no {rule} evidence")
        if counts[f"unflagged:{rule}"]:
            failures.append(f"evidence_items: {counts[f'unflagged:{rule}']} row(s) with {rule} evidence but not {flag}")
    return failures


def _fail(failures: list[str]) -> None:
    raise ValueError("Silver Stage 3 runtime checks failed:\n- " + "\n- ".join(failures))


def _schema_failures(silver_facilities: DataFrame, stage3: DataFrame, kept: list[str]) -> list[str]:
    input_types = dict(silver_facilities.dtypes)
    expected = {name: input_types[name] for name in kept} | {column.name: column.type for column in columns.NEW_COLUMNS}
    actual = dict(stage3.dtypes)
    failures = []
    for name, kind in expected.items():
        if name not in actual:
            failures.append(f"{name}: column is missing")
        elif actual[name] != kind:
            failures.append(f"{name}: type is {actual[name]}, expected {kind}")
    failures += [f"{name}: unexpected column" for name in actual if name not in expected]
    return failures
