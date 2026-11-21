"""The Silver base pipeline: one private function per step of the spec's Order of steps.

`build_silver_base` runs the steps in the order spec #1 requires. Steps not yet
built are marked `TODO(#n)` with the ticket that adds them; slot each new step
in at its marker as a private `_step` function that takes and returns a DataFrame.
"""

from pyspark.sql import DataFrame
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
    # 2. TODO(#4): record original list lengths; set needs_investigation, truncated_columns.
    # 3. Drop columns.
    df = _drop_unused_columns(df)
    # 4. Normalize whitespace, then Missing values.
    df = _normalize_text_columns(df)
    # 5. TODO(#4): parse lists. TODO(#5, #6): Spelling fixes and formatting of values
    #    and list items. TODO(#4): remove empty and Duplicate items; empty list -> NULL.
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


def _drop_unused_columns(df: DataFrame) -> DataFrame:
    return df.drop(*_DROPPED_COLUMNS)


def _normalize_text_columns(df: DataFrame) -> DataFrame:
    """Whitespace, then Missing values, on every string column's raw text.

    In list columns a value merely containing the hidden-email placeholder is not
    Missing as a whole (its other items may be real); #4 applies the full rule per item.
    """
    text_columns = [f.name for f in df.schema.fields if isinstance(f.dataType, T.StringType)]
    return df.withColumns(
        {
            name: clean_text(F.col(name), placeholder_anywhere=name not in _LIST_COLUMNS)
            for name in text_columns
        }
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
