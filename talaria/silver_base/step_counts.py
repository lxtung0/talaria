"""Silver base before/after counts per step (spec #1, "Runtime checks").

`step_counts` compares the bronze facilities snapshot with the output of
`build_silver_base`, so the cleaning module keeps its single entry point and
never has to report on itself. The notebook prints the result with
`format_step_counts`.

It reuses the pipeline's column lists and per-value rules (package internals)
so the counts describe exactly the columns and rules Silver base applies.
"""

from collections.abc import Callable

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from talaria.silver_base import formatting, spelling
from talaria.silver_base.pipeline import _DROPPED_COLUMNS, _LIST_COLUMNS, _RENAMES, _as_array
from talaria.silver_base.text import _EMAIL_PLACEHOLDER, clean_text, normalize_whitespace

Counts = dict[str, dict[str, int]]


def step_counts(bronze: DataFrame, silver: DataFrame) -> Counts:
    """Counts per step, as {section: {label: count}}.

    - `rows`: bronze rows, Description fragments and Exact duplicates removed, Silver base rows.
    - `nulls`: values set to NULL, by the Missing-value spelling they had.
    - `items_removed`: empty and Duplicate items removed, per list column.
    - `spelling_fixes`: values and list items changed, per alias table.
    - `formatting`: values and list items formatted vs left unchanged, per formatted column.
    - `flags`: Facilities with each flag set.

    `silver` must be `build_silver_base(bronze)`.
    """
    bronze_rows = bronze.count()
    real = bronze.where(F.col("source_urls").isNotNull())
    real_rows = real.count()
    kept = real.distinct()
    distinct_rows = kept.count()

    # Bronze row next to its Silver base row; Silver base columns are prefixed `silver.`.
    silver_prefixed = silver.select([F.col(f"`{c}`").alias(f"silver.{c}") for c in silver.columns])
    paired = kept.join(silver_prefixed, kept["unique_id"] == silver_prefixed["`silver.unique_id`"])

    counts = {
        "rows": {
            "bronze": bronze_rows,
            "description_fragments_removed": bronze_rows - real_rows,
            "exact_duplicates_removed": real_rows - distinct_rows,
            "silver_base": silver.count(),
        },
        "nulls": _nulls(paired, kept),
        "items_removed": _items_removed(paired),
        "spelling_fixes": _spelling_fixes(kept),
        "formatting": _formatting(kept),
        "flags": _flags(silver),
    }
    return counts


def _silver(name: str) -> Column:
    """The Silver base column that bronze column `name` became."""
    return F.col(f"`silver.{_RENAMES.get(name, name)}`")


_MISSING_TYPES = ["null_text", "empty_text", "empty_array_text", "hidden_email"]


def _nulls(paired: DataFrame, kept: DataFrame) -> dict[str, int]:
    text_columns = [
        f.name
        for f in kept.schema.fields
        if isinstance(f.dataType, T.StringType) and f.name not in _DROPPED_COLUMNS
    ]
    missing_type = {name: _missing_type(F.col(name), list_column=name in _LIST_COLUMNS) for name in text_columns}
    list_emptied = [
        F.when(F.col(name).isNotNull() & missing_type[name].isNull() & _silver(name).isNull(), 1)
        for name in _LIST_COLUMNS
    ]
    row = paired.agg(
        *[
            sum((F.count(F.when(type_ == t, 1)) for type_ in missing_type.values()), F.lit(0)).alias(t)
            for t in _MISSING_TYPES
        ],
        sum((F.count(c) for c in list_emptied), F.lit(0)).alias("list_empty_after_cleanup"),
        F.count(F.when(F.expr("try_cast(numberDoctors AS int)") == 0, 1)).alias("zero_doctors"),
    ).first()
    return row.asDict()


def _items_removed(paired: DataFrame) -> dict[str, int]:
    """Bronze items minus Silver base items, per list column: empty and Duplicate items removed.

    A whole Missing value is a NULL, not an item, so it counts zero items.
    """
    row = paired.agg(
        *[
            (
                F.sum(
                    F.when(
                        _missing_type(F.col(name), list_column=True).isNull(),
                        _item_count(_as_array(normalize_whitespace(F.col(name)))),
                    )
                )
                - F.sum(_item_count(_silver(name)))
            ).alias(name)
            for name in _LIST_COLUMNS
        ]
    ).first()
    return {_RENAMES.get(name, name): row[name] or 0 for name in _LIST_COLUMNS}


def _item_count(items: Column) -> Column:
    """Number of items, 0 for a NULL list (Spark's `size` gives -1 there)."""
    return F.coalesce(F.when(items.isNotNull(), F.size(items)), F.lit(0))


# Per alias table: the bronze column, its Spelling fix rule, and what the value
# would be without any alias (the rule's plain case-shaping). A value whose rule
# output differs from that is a Spelling fix.
_SPELLING_RULES: dict[str, tuple[str, Callable[[Column], Column], Callable[[Column], Column]]] = {
    "facility_type": ("facilityTypeId", spelling.facility_type, F.lower),
    "operator_type": ("operatorTypeId", spelling.operator_type, F.lower),
    "affiliation_type": ("affiliationTypeIds", spelling.affiliation_type, F.lower),
    "state": ("address_stateOrRegion", spelling.state, lambda v: v),
    "city": ("address_city", spelling.city, F.initcap),
    "specialty": ("specialties", spelling.specialty, lambda v: v),
}


def _spelling_fixes(kept: DataFrame) -> dict[str, int]:
    row = kept.agg(
        *[
            _count_values(name, lambda v, rule=rule, plain=plain: rule(v) != plain(v)).alias(table)
            for table, (name, rule, plain) in _SPELLING_RULES.items()
        ]
    ).first()
    return {table: row[table] or 0 for table in _SPELLING_RULES}


# Formatted columns (spec #1, "Formatting"), by bronze name, with their rule.
_FORMAT_RULES: dict[str, Callable[[Column], Column]] = {
    "address_zipOrPostcode": formatting.format_pin,
    "officialPhone": formatting.format_phone,
    "phone_numbers": formatting.format_phone,
    "email": formatting.format_email,
    "officialWebsite": formatting.format_url,
    "websites": formatting.format_url,
    "facebookLink": formatting.format_url,
}


def _formatting(kept: DataFrame) -> dict[str, int]:
    """Per formatted column, values (or items) the rule rewrote vs left as they were.

    "Unchanged" covers both values already in the standard format and values
    that could not be formatted.
    """
    columns = []
    for name, rule in _FORMAT_RULES.items():
        out = _RENAMES.get(name, name)
        columns.append(_count_values(name, lambda v, rule=rule: rule(v) != v).alias(f"{out}_formatted"))
        columns.append(_count_values(name, lambda v, rule=rule: rule(v) == v).alias(f"{out}_unchanged"))
    row = kept.agg(*columns).first()
    return {key: value or 0 for key, value in row.asDict().items()}


def _flags(silver: DataFrame) -> dict[str, int]:
    """Facilities with each flag set: Needs investigation, each Truncated list column, zero beds."""
    list_columns = [_RENAMES.get(name, name) for name in _LIST_COLUMNS]
    row = silver.agg(
        F.count(F.when(F.col("needs_investigation"), 1)).alias("needs_investigation"),
        *[
            F.count(F.when(F.array_contains(F.col("truncated_columns"), name), 1)).alias(f"truncated_{name}")
            for name in list_columns
        ],
        F.count(F.when(F.col("flag_zero_beds"), 1)).alias("zero_beds"),
    ).first()
    return row.asDict()


def _count_values(name: str, predicate: Callable[[Column], Column]) -> Column:
    """Aggregate: how many cleaned values of bronze column `name` (items, for a list column) match `predicate`.

    Values are cleaned as Silver base cleans them before its fixes run:
    whitespace normalized, Missing values NULL, lists parsed.
    """
    raw = F.col(name)
    if name in _LIST_COLUMNS:
        items = F.transform(_as_array(clean_text(raw, placeholder_anywhere=False)), lambda item: clean_text(item))
        matching = F.filter(items, lambda item: item.isNotNull() & predicate(item))
        return F.sum(_item_count(matching))
    value = clean_text(raw)
    return F.count(F.when(value.isNotNull() & predicate(value), 1))


def _missing_type(raw: Column, *, list_column: bool) -> Column:
    """Which Missing-value spelling a raw value has, or NULL when it is not Missing.

    Mirrors the Missing-value rule: in a list column only a whole value equal to
    the hidden-email placeholder is Missing (its items are judged one by one).
    """
    value = normalize_whitespace(raw)
    placeholder = value == _EMAIL_PLACEHOLDER if list_column else value.contains(_EMAIL_PLACEHOLDER)
    return (
        F.when(F.lower(value) == "null", "null_text")
        .when(value == "", "empty_text")
        .when(value == "[]", "empty_array_text")
        .when(placeholder, "hidden_email")
    )


def format_step_counts(counts: Counts) -> str:
    """One indented `label: count` line per count, grouped by section."""
    lines = []
    for section, values in counts.items():
        lines.append(section)
        lines.extend(f"  {label}: {value:,}" for label, value in values.items())
    return "\n".join(lines)
