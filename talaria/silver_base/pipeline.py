"""The Silver base pipeline: one private function per step of the spec's Order of steps.

`build_silver_base` runs the steps in the order spec #1 requires. Each step is a
private `_step` function that takes and returns a DataFrame. Which columns a step
touches, and the per-column rules, live in `columns.py`.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from talaria.silver_base import columns, state_check
from talaria.silver_base.checks import unique_id_counts, unique_id_failures
from talaria.silver_base.text import clean_item, clean_list_text, clean_text, lookup, text_item_key


def build_silver_base(bronze: DataFrame, pincodes: DataFrame) -> DataFrame:
    """Turn the bronze facilities snapshot into Silver base, one row per Facility.

    `pincodes` is the bronze India Post pincode directory, the reference each
    Facility's state is checked against (#9).

    Raises ValueError if `unique_id` is null or repeated after cleanup, or if a
    non-missing value fails to convert to its type.
    """
    # 1. Objectively bad rows.
    df = _remove_description_fragments(bronze)
    df = _collapse_exact_duplicates(df)
    # 2. Original list lengths, before any cleanup, set the truncation flags.
    df = _flag_truncated_lists(df)
    # 3. Drop columns.
    df = _drop_unused_columns(df)
    # 4. Normalize whitespace, then Missing values.
    df = _normalize_text_columns(df)
    # 5. Parse lists, then Spelling fixes and formatting, then remove empty and
    #    Duplicate items; empty list -> NULL.
    df = _parse_list_columns(df)
    df = _fix_and_format_values(df)
    df = _remove_empty_and_duplicate_items(df)
    # 6. Zero-doctors and zero-beds rules, repeated address line, date rewrite.
    df = _apply_value_rules(df)
    # 6b. State checked against the pincode directory (#9): the one value Silver
    #     base takes from another table. Needs the state Spelling fix and PIN format.
    df = state_check.check_state(df, pincodes)
    # 7. Validate (one Spark job), convert types, then rename columns.
    _validate(df)
    df = _convert_types(df)
    return _rename_columns(df)


def _remove_description_fragments(df: DataFrame) -> DataFrame:
    return df.where(~columns.is_description_fragment())


def _collapse_exact_duplicates(df: DataFrame) -> DataFrame:
    return df.dropDuplicates()


# Spec #1, "Truncation": the source's hard cap on list length.
_LIST_CAP = 50


def _flag_truncated_lists(df: DataFrame) -> DataFrame:
    """A Truncated list's original JSON array has exactly `_LIST_CAP` items, empty and duplicate ones included.

    `truncated_columns` names those columns (by their output names), NULL when none;
    `needs_investigation` is true when there is at least one.
    """
    truncated = F.filter(
        F.array(
            *[
                F.when(
                    columns.original_list_size(F.col(name)) == _LIST_CAP,
                    F.lit(columns.output_name(name)),
                )
                for name in columns.LIST_COLUMNS
            ]
        ),
        lambda name: name.isNotNull(),
    )
    return df.withColumns(
        {
            "needs_investigation": F.size(truncated) > 0,
            "truncated_columns": F.when(F.size(truncated) > 0, truncated),
        }
    )


def _drop_unused_columns(df: DataFrame) -> DataFrame:
    return df.drop(*columns.DROPPED_COLUMNS)


def _normalize_text_columns(df: DataFrame) -> DataFrame:
    """Whitespace, then Missing values, on every string column's raw text.

    A plain text value has the hidden-email placeholder cut out. A list column's
    raw text keeps it: only its items are judged, in `_parse_list_columns`.
    """
    text_columns = [f.name for f in df.schema.fields if isinstance(f.dataType, T.StringType)]
    return df.withColumns(
        {
            name: clean_list_text(F.col(name)) if name in columns.LIST_COLUMNS else clean_text(F.col(name))
            for name in text_columns
        }
    )


def _parse_list_columns(df: DataFrame) -> DataFrame:
    """JSON-array text to `array<string>`, each item whitespace- and Missing-value-cleaned.

    A value that is not a JSON array (such as a lone email address) becomes a
    one-item list. Missing items, and items holding the hidden-email placeholder,
    become NULL here and are dropped later.
    """
    return df.withColumns(
        {name: F.transform(columns.parse_list(F.col(name)), clean_item) for name in columns.LIST_COLUMNS}
    )


def _fix_and_format_values(df: DataFrame) -> DataFrame:
    """Spelling fixes and formatting of values and list items, before Duplicate items are removed.

    Runs on bronze column names, after lists are parsed into `array<string>` and
    before empty and Duplicate items are removed, so format-only variants collapse.
    Each rule (`columns.SPELLING_FIXES`, `columns.FORMATTING`) maps one text value to
    its fixed value, applied to a plain text column directly and to a list
    column's every item. An item a rule turns into NULL is dropped later.
    """
    rules = {fix.column: fix.fix for fix in columns.SPELLING_FIXES.values()} | columns.FORMATTING
    return df.withColumns({name: _apply_to_value_or_items(df, name, rule) for name, rule in rules.items()})


def _apply_to_value_or_items(df: DataFrame, name: str, rule: columns.Rule) -> Column:
    if isinstance(df.schema[name].dataType, T.ArrayType):
        return F.transform(F.col(name), rule)
    return rule(F.col(name))


def _remove_empty_and_duplicate_items(df: DataFrame) -> DataFrame:
    """Drop NULL items and Duplicate items (keeping the first, in order); an empty list becomes NULL.

    Text lists compare items by `text_item_key`; identifier lists
    (`columns.IDENTIFIER_LIST_COLUMNS`) by exact equality, since case and punctuation matter in them.
    """

    def clean(name: str) -> Column:
        items = F.filter(F.col(name), lambda item: item.isNotNull())
        deduped = F.array_distinct(items) if name in columns.IDENTIFIER_LIST_COLUMNS else _dedupe_by_text_key(items)
        return F.when(F.size(deduped) > 0, deduped)

    return df.withColumns({name: clean(name) for name in columns.LIST_COLUMNS})


def _dedupe_by_text_key(items: Column) -> Column:
    """Keep each item whose key no earlier item shares (first spelling and order kept)."""
    keys = F.transform(items, text_item_key)
    return F.filter(items, lambda item, i: ~F.array_contains(F.slice(keys, 1, i), keys[i]))


def _apply_value_rules(df: DataFrame) -> DataFrame:
    """Spec #1, "Other rules". Runs on text, before types are converted."""
    doctors = F.expr("try_cast(numberDoctors AS int)")
    beds = F.expr("try_cast(capacity AS int)")
    return df.withColumns(
        {
            # An unrecorded count, not a Facility with no doctors.
            "numberDoctors": F.when(doctors == 0, F.lit(None).cast("string")).otherwise(F.col("numberDoctors")),
            # 0 beds is kept; Silver facilities decides whether it is real.
            "flag_zero_beds": F.coalesce(beds == 0, F.lit(False)),
            # Both lines are already whitespace-normalized (step 4).
            "address_line3": F.when(
                F.col("address_line3") == F.col("address_line2"), F.lit(None).cast("string")
            ).otherwise(F.col("address_line3")),
            "recency_of_page_update": _month_year_to_iso(F.col("recency_of_page_update")),
        }
    )


_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
_MONTH_NUMBERS = {name: f"{i:02d}" for i, name in enumerate(_MONTHS, 1)}
_MONTH_YEAR = rf"^({'|'.join(_MONTHS)}) ([0-9]{{4}})$"


def _month_year_to_iso(col: Column) -> Column:
    """`October 2025` -> `2025-10-01`, still text. Anything else (`3 weeks ago`) is unchanged."""
    lowered = F.lower(col)
    iso = F.concat_ws(
        "-",
        F.regexp_extract(lowered, _MONTH_YEAR, 2),
        lookup(_MONTH_NUMBERS, F.regexp_extract(lowered, _MONTH_YEAR, 1)),
        F.lit("01"),
    )
    return F.when(lowered.rlike(_MONTH_YEAR), iso).otherwise(col)


def _validate(df: DataFrame) -> None:
    """Fail the run, in one Spark job, if Silver base would not be one typed row per Facility.

    - `unique_id` is null or repeated.
    - A non-missing value fails to convert to its type (spec #1, "Types"). Missing
      values are already NULL (step 4), so a NULL after conversion from a non-NULL
      value is a failure, never silently dropped.
    """
    counts = df.agg(
        *unique_id_counts(),
        *[
            F.count(F.when(F.col(name).isNotNull() & _converted(name).isNull(), 1)).alias(f"not_converted:{name}")
            for name in columns.TYPES
        ],
    ).first()
    failures = [f"{failure} after cleanup" for failure in unique_id_failures(counts)]
    not_converted = {name: counts[f"not_converted:{name}"] for name in columns.TYPES if counts[f"not_converted:{name}"]}
    if not_converted:
        detail = ", ".join(f"{name} ({n} value(s) not {columns.TYPES[name]})" for name, n in not_converted.items())
        failures.append(f"values failed to convert: {detail}")
    if failures:
        raise ValueError("Silver base failed:\n- " + "\n- ".join(failures))


def _converted(name: str) -> Column:
    return F.expr(f"try_cast(`{name}` AS {columns.TYPES[name]})")


def _convert_types(df: DataFrame) -> DataFrame:
    """Spec #1, "Types". `_validate` has already checked that every value converts."""
    return df.withColumns({name: _converted(name) for name in columns.TYPES})


def _rename_columns(df: DataFrame) -> DataFrame:
    return df.withColumnsRenamed(columns.RENAMES)
