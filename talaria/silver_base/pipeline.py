"""The Silver base pipeline: one private function per step of the spec's Order of steps.

`build_silver_base` runs the steps in the order spec #1 requires. Steps not yet
built are marked `TODO(#n)` with the ticket that adds them; slot each new step
in at its marker as a private `_step` function that takes and returns a DataFrame.
"""

from collections.abc import Callable

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from talaria.silver_base.text import clean_text

# Spec #1, "Columns dropped (16)".
_DROPPED_COLUMNS = [
    # Not used.
    "acceptsVolunteers",
    "address_country",
    "address_countryCode",
    "countries",
    "custom_logo_presence",
    "engagement_metrics_n_engagements",
    "engagement_metrics_n_followers",
    "engagement_metrics_n_likes",
    "organization_type",
    "post_metrics_most_recent_social_media_post_date",
    "post_metrics_post_count",
    "source",
    # Copies of other columns.
    "coordinates",  # equals latitude/longitude
    "content_table_id",  # equals source_content_id
    # Unused source bookkeeping.
    "source_types",
    "source_ids",
]


# Spec #1, "List columns": JSON-array text in bronze.
_LIST_COLUMNS = [
    "specialties",
    "procedure",
    "equipment",
    "capability",
    "phone_numbers",
    "websites",
    "source_urls",
    "affiliationTypeIds",
    "email",
]


# Spec #1, "Renames to snake_case". Columns not listed keep their names.
_RENAMES = {
    "officialPhone": "official_phone",
    "officialWebsite": "official_website",
    "yearEstablished": "year_established",
    "facebookLink": "facebook_link",
    "address_stateOrRegion": "address_state",
    "address_zipOrPostcode": "address_pincode",
    "facilityTypeId": "facility_type",
    "operatorTypeId": "operator_type",
    "affiliationTypeIds": "affiliation_types",
    "numberDoctors": "number_doctors",
    "capacity": "bed_count",
}


def build_silver_base(bronze: DataFrame) -> DataFrame:
    """Turn the bronze facilities snapshot into Silver base, one row per Facility.

    Raises ValueError if `unique_id` is null or repeated after cleanup.
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
    # 6. TODO(#7): zero-doctors and zero-beds rules, repeated address line, date rewrite.
    # 7. TODO(#7): convert types. Then rename columns.
    df = _rename_columns(df)
    _check_unique_id(df)
    return df


def _remove_description_fragments(df: DataFrame) -> DataFrame:
    """A Description fragment has no `source_urls`; every real Facility has some."""
    return df.where(F.col("source_urls").isNotNull())


def _collapse_exact_duplicates(df: DataFrame) -> DataFrame:
    return df.dropDuplicates()


_LIST_SCHEMA = T.ArrayType(T.StringType())

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
                    F.size(F.from_json(F.col(name), _LIST_SCHEMA)) == _LIST_CAP,
                    F.lit(_RENAMES.get(name, name)),
                )
                for name in _LIST_COLUMNS
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
    return df.drop(*_DROPPED_COLUMNS)


def _normalize_text_columns(df: DataFrame) -> DataFrame:
    """Whitespace, then Missing values, on every string column's raw text.

    In list columns a value merely containing the hidden-email placeholder is not
    Missing as a whole (its other items may be real); `_parse_list_columns` applies the full rule per item.
    """
    text_columns = [f.name for f in df.schema.fields if isinstance(f.dataType, T.StringType)]
    return df.withColumns(
        {
            name: clean_text(F.col(name), placeholder_anywhere=name not in _LIST_COLUMNS)
            for name in text_columns
        }
    )


def _parse_list_columns(df: DataFrame) -> DataFrame:
    """JSON-array text to `array<string>`, each item whitespace- and Missing-value-cleaned.

    A value that is not a JSON array (such as a lone email address) becomes a
    one-item list. Missing items become NULL here and are dropped later.
    """
    return df.withColumns(
        {
            name: F.transform(_as_array(F.col(name)), lambda item: clean_text(item))
            for name in _LIST_COLUMNS
        }
    )


def _as_array(raw: Column) -> Column:
    parsed = F.from_json(raw, _LIST_SCHEMA)
    return F.when(raw.isNull(), F.lit(None).cast("array<string>")).otherwise(
        F.coalesce(parsed, F.array(raw))
    )


def _fix_and_format_values(df: DataFrame) -> DataFrame:
    """Spelling fixes and formatting of values and list items, before Duplicate items are removed.

    Runs on bronze column names, after lists are parsed into `array<string>` and
    before empty and Duplicate items are removed, so format-only variants collapse.
    Add a rule as an entry in `_VALUE_RULES`: a function from one text value to
    its fixed value, applied to a plain text column directly and to a list
    column's every item. An item a rule turns into NULL is dropped later.
    """
    return df.withColumns(
        {name: _apply_to_values(df, name, rule) for name, rule in _VALUE_RULES.items()}
    )


# Per-column Spelling fix / formatting rules, keyed by bronze column name.
# TODO(#5): Spelling fixes (facilityTypeId, operatorTypeId, affiliationTypeIds,
#   address_stateOrRegion, address_city, specialties).
# TODO(#6): formatting (officialPhone, phone_numbers, email, officialWebsite,
#   websites, facebookLink, address_zipOrPostcode). source_urls is never formatted.
_VALUE_RULES: dict[str, Callable[[Column], Column]] = {}


def _apply_to_values(df: DataFrame, name: str, rule: Callable[[Column], Column]) -> Column:
    if isinstance(df.schema[name].dataType, T.ArrayType):
        return F.transform(F.col(name), lambda item: rule(item))
    return rule(F.col(name))


def _remove_empty_and_duplicate_items(df: DataFrame) -> DataFrame:
    """Drop NULL items and Duplicate items (keeping the first, in order); an empty list becomes NULL.

    Text lists compare items by `_text_item_key`; identifier lists (`_IDENTIFIER_LIST_COLUMNS`)
    by exact equality, since case and punctuation matter in them.
    """

    def clean(name: str) -> Column:
        items = F.filter(F.col(name), lambda item: item.isNotNull())
        deduped = F.array_distinct(items) if name in _IDENTIFIER_LIST_COLUMNS else _dedupe_by_text_key(items)
        return F.when(F.size(deduped) > 0, deduped)

    return df.withColumns({name: clean(name) for name in _LIST_COLUMNS})


# Spec #1, "Duplicate items in identifier lists": deduped on exact equality.
_IDENTIFIER_LIST_COLUMNS = {"phone_numbers", "websites", "email", "source_urls"}


def _text_item_key(item: Column) -> Column:
    """Lower-case, letters and digits only, one trailing `s` removed: equal keys are Duplicate items."""
    alphanumeric = F.regexp_replace(F.lower(item), r"[^\p{L}\p{N}]", "")
    return F.regexp_replace(alphanumeric, "s$", "")


def _dedupe_by_text_key(items: Column) -> Column:
    """Keep each item whose key no earlier item shares (first spelling and order kept)."""
    return F.filter(
        items,
        lambda item, i: ~F.exists(
            F.slice(items, 1, i), lambda earlier: _text_item_key(earlier) == _text_item_key(item)
        ),
    )


def _rename_columns(df: DataFrame) -> DataFrame:
    return df.withColumnsRenamed(_RENAMES)


def _check_unique_id(df: DataFrame) -> None:
    """Fail the run if `unique_id` is null or repeated: one row per Facility."""
    counts = df.agg(
        F.count(F.lit(1)).alias("rows"),
        F.count("unique_id").alias("non_null"),
        F.countDistinct("unique_id").alias("distinct"),
    ).first()
    if counts.non_null != counts.rows:
        raise ValueError(f"unique_id is null in {counts.rows - counts.non_null} row(s) after cleanup")
    if counts.distinct != counts.rows:
        raise ValueError(
            f"unique_id is repeated: {counts.rows} rows but {counts.distinct} distinct ids after cleanup"
        )
