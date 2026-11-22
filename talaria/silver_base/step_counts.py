"""Silver base before/after counts per step (spec #1, "Runtime checks").

`step_counts` compares the bronze facilities snapshot with the output of
`build_silver_base`, so the cleaning module keeps its single entry point and
never has to report on itself. The notebook prints the result with
`format_step_counts`.

The columns and per-value rules come from `columns.py`, the same tables the
pipeline applies, so the counts describe exactly what Silver base does.
"""

from collections.abc import Callable

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from talaria.silver_base import columns, spelling, state_check
from talaria.silver_base.text import clean_item, clean_list_text, clean_text, missing_spelling, normalize_whitespace

Counts = dict[str, dict[str, int]]


def step_counts(bronze: DataFrame, silver: DataFrame) -> Counts:
    """Counts per step, as {section: {label: count}}.

    - `rows`: bronze rows, Description fragments and Exact duplicates removed, Silver base rows.
    - `nulls`: values set to NULL, by the Missing-value spelling they had.
    - `items_removed`: empty and Duplicate items removed, per list column.
    - `spelling_fixes`: values and list items changed, per alias table (British spelling per column).
    - `formatting`: values and list items formatted vs left unchanged, per formatted column.
    - `flags`: Facilities with each flag set.
    - `state_check`: states corrected by the pincode directory check (#9).

    `silver` must be `build_silver_base(bronze, pincodes)`.
    """
    # Bronze row counts: two Spark jobs.
    raw_counts = bronze.agg(
        F.count(F.lit(1)).alias("bronze"), F.count(F.when(~columns.is_description_fragment(), 1)).alias("real")
    ).first()
    facilities = bronze.where(~columns.is_description_fragment()).distinct()
    facility_rows = facilities.count()

    # Bronze row next to its Silver base row; Silver base columns are prefixed `silver.`.
    silver_prefixed = silver.select([F.col(f"`{c}`").alias(f"silver.{c}") for c in silver.columns])
    paired = facilities.join(silver_prefixed, facilities["unique_id"] == silver_prefixed["`silver.unique_id`"])

    # Every other count, in one Spark job over the paired rows.
    sections = {
        "nulls": _nulls(facilities),
        "items_removed": _items_removed(),
        "spelling_fixes": _spelling_fixes(),
        "formatting": _formatting(),
        "flags": _flags(),
        "state_check": _state_check(),
    }
    row = paired.agg(
        F.count(F.col("`silver.unique_id`")).alias("silver_base"),
        *[count.alias(f"{section}:{label}") for section, counts in sections.items() for label, count in counts.items()],
    ).first()

    return {
        "rows": {
            "bronze": raw_counts.bronze,
            "description_fragments_removed": raw_counts.bronze - raw_counts.real,
            "exact_duplicates_removed": raw_counts.real - facility_rows,
            "silver_base": row.silver_base,
        },
        **{
            section: {label: row[f"{section}:{label}"] or 0 for label in counts}
            for section, counts in sections.items()
        },
    }


# Each section below is {label: aggregate Column} over the paired bronze and Silver base rows.


def _silver(name: str) -> Column:
    """The Silver base column that bronze column `name` became."""
    return F.col(f"`silver.{columns.output_name(name)}`")


_MISSING_TYPES = ["null_text", "empty_text", "empty_array_text", "hidden_email"]


def _nulls(facilities: DataFrame) -> dict[str, Column]:
    text_columns = [
        f.name
        for f in facilities.schema.fields
        if isinstance(f.dataType, T.StringType) and f.name not in columns.DROPPED_COLUMNS
    ]
    missing_type = {name: missing_spelling(normalize_whitespace(F.col(name))) for name in text_columns}
    list_emptied = [
        F.when(F.col(name).isNotNull() & missing_type[name].isNull() & _silver(name).isNull(), 1)
        for name in columns.LIST_COLUMNS
    ]
    return {
        **{
            t: sum((F.count(F.when(type_ == t, 1)) for type_ in missing_type.values()), F.lit(0))
            for t in _MISSING_TYPES
        },
        "list_empty_after_cleanup": sum((F.count(c) for c in list_emptied), F.lit(0)),
        "zero_doctors": F.count(F.when(F.expr("try_cast(numberDoctors AS int)") == 0, 1)),
    }


def _items_removed() -> dict[str, Column]:
    """Bronze items minus Silver base items, per list column: empty and Duplicate items removed.

    A whole Missing value is a NULL, not an item, so it counts zero items.
    """
    return {
        columns.output_name(name): F.sum(_item_count(columns.parse_list(clean_list_text(F.col(name)))))
        - F.sum(_item_count(_silver(name)))
        for name in columns.LIST_COLUMNS
    }


def _item_count(items: Column) -> Column:
    """Number of items, 0 for a NULL list (Spark's `size` gives -1 there)."""
    return F.coalesce(F.when(items.isNotNull(), F.size(items)), F.lit(0))


def _spelling_fixes() -> dict[str, Column]:
    return {
        table: _count_values(fix.column, lambda v, fix=fix: fix.fix(v) != fix.plain(v))
        for table, fix in columns.SPELLING_FIXES.items()
    }


def _formatting() -> dict[str, Column]:
    """Per formatted column, values (or items) the rule rewrote vs left as they were.

    "Unchanged" covers both values already in the standard format and values
    that could not be formatted.
    """
    counts = {}
    for name, rule in columns.FORMATTING.items():
        out = columns.output_name(name)
        counts[f"{out}_formatted"] = _count_values(name, lambda v, rule=rule: rule(v) != v)
        counts[f"{out}_unchanged"] = _count_values(name, lambda v, rule=rule: rule(v) == v)
    return counts


def _flags() -> dict[str, Column]:
    """Facilities with each flag set: Needs investigation, each Truncated list column, zero beds, the state check."""

    def flagged(condition: Column) -> Column:
        return F.count(F.when(condition, 1))

    return {
        "needs_investigation": flagged(F.col("`silver.needs_investigation`")),
        **{
            f"truncated_{name}": flagged(F.array_contains(F.col("`silver.truncated_columns`"), name))
            for name in map(columns.output_name, columns.LIST_COLUMNS)
        },
        "zero_beds": flagged(F.col("`silver.flag_zero_beds`")),
        **{flag.removeprefix("flag_"): flagged(F.col(f"`silver.{flag}`")) for flag in state_check.FLAGS},
    }


def _state_check() -> dict[str, Column]:
    """Facilities whose Silver base state differs from their Spelling-fixed bronze state."""
    fixed = spelling.state(clean_text(F.col("address_stateOrRegion")))
    return {"states_corrected": F.count(F.when(~fixed.eqNullSafe(_silver("address_stateOrRegion")), 1))}


def _count_values(name: str, predicate: Callable[[Column], Column]) -> Column:
    """Aggregate: how many cleaned values of bronze column `name` (items, for a list column) match `predicate`.

    Values are cleaned as Silver base cleans them before its fixes run:
    whitespace normalized, Missing values NULL, lists parsed.
    """
    raw = F.col(name)
    if name in columns.LIST_COLUMNS:
        items = F.transform(columns.parse_list(clean_list_text(raw)), clean_item)
        matching = F.filter(items, lambda item: item.isNotNull() & predicate(item))
        return F.sum(_item_count(matching))
    value = clean_text(raw)
    return F.count(F.when(value.isNotNull() & predicate(value), 1))


def format_step_counts(counts: Counts) -> str:
    """One indented `label: count` line per count, grouped by section."""
    lines = []
    for section, values in counts.items():
        lines.append(section)
        lines.extend(f"  {label}: {value:,}" for label, value in values.items())
    return "\n".join(lines)
