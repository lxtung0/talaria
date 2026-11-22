"""Which columns Silver base touches, and which rule it applies to each (spec #1).

The one home for these tables: `pipeline` applies them and `step_counts` reports
on them, so adding a column or a rule is one edit here. All names are bronze
column names unless they say otherwise; `output_name` gives the Silver base name.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pyspark.sql import Column
from pyspark.sql import functions as F
from pyspark.sql import types as T

from talaria.silver_base import formatting, spelling

Rule = Callable[[Column], Column]

# Spec #1, "Columns dropped".
DROPPED_COLUMNS = [
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
    "yearEstablished",
    # Copies of other columns.
    "coordinates",  # equals latitude/longitude
    "content_table_id",  # equals source_content_id
    # Unused source bookkeeping.
    "source_types",
    "source_ids",
]

# Spec #1, "List columns": JSON-array text in bronze.
LIST_COLUMNS = [
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

# Spec #1, "Duplicate items in identifier lists": deduped on exact equality.
# The other list columns are text lists, deduped by their Duplicate-item key.
IDENTIFIER_LIST_COLUMNS = {"phone_numbers", "websites", "email", "source_urls"}

# Spec #1, "Types": bronze text columns converted to these types. `latitude` and
# `longitude` are already double; the PIN, official phone and
# `recency_of_page_update` stay text.
TYPES = {
    "numberDoctors": "int",
    "capacity": "int",
    "distinct_social_media_presence_count": "int",
    "number_of_facts_about_the_organization": "int",
    "area": "double",
    "affiliated_staff_presence": "boolean",
}

# Spec #1, "Renames to snake_case". Columns not listed keep their names.
RENAMES = {
    "officialPhone": "official_phone",
    "officialWebsite": "official_website",
    "facebookLink": "facebook_link",
    "address_stateOrRegion": "address_state",
    "address_zipOrPostcode": "address_pincode",
    "facilityTypeId": "facility_type",
    "operatorTypeId": "operator_type",
    "affiliationTypeIds": "affiliation_types",
    "numberDoctors": "number_doctors",
    "capacity": "bed_count",
}


def output_name(name: str) -> str:
    """The Silver base name of bronze column `name`."""
    return RENAMES.get(name, name)


def is_description_fragment() -> Column:
    """A Description fragment has no `source_urls`; every real Facility has some."""
    return F.col("source_urls").isNull()


_LIST_SCHEMA = T.ArrayType(T.StringType())


def parse_list(raw: Column) -> Column:
    """JSON-array text to `array<string>`; any other text (a lone email address) is a one-item list."""
    return F.when(raw.isNull(), F.lit(None).cast(_LIST_SCHEMA)).otherwise(
        F.coalesce(F.from_json(raw, _LIST_SCHEMA), F.array(raw))
    )


def original_list_size(raw: Column) -> Column:
    """Items in the raw JSON array, empty and duplicate ones included; NULL when it is not a JSON array."""
    return F.size(F.from_json(raw, _LIST_SCHEMA))


@dataclass(frozen=True)
class SpellingFix:
    """One alias table applied to one column.

    `plain` is what the value would be without any alias (the rule's case
    shaping alone), so a value where `fix` and `plain` differ is a Spelling fix.
    """

    column: str
    fix: Rule
    plain: Rule


def _unchanged(col: Column) -> Column:
    return col


# Spec #1, "Spelling fixes", keyed by the label step counts report them under.
SPELLING_FIXES = {
    "facility_type": SpellingFix("facilityTypeId", spelling.facility_type, F.lower),
    "operator_type": SpellingFix("operatorTypeId", spelling.operator_type, F.lower),
    "affiliation_type": SpellingFix("affiliationTypeIds", spelling.affiliation_type, F.lower),
    "state": SpellingFix("address_stateOrRegion", spelling.state, _unchanged),
    "city": SpellingFix("address_city", spelling.city, F.initcap),
    **{
        f"british_spelling_{name}": SpellingFix(name, spelling.american_spelling, _unchanged)
        for name in ["specialties", "procedure", "equipment", "capability"]
    },
}

# Spec #1, "Formatting", by column. `source_urls` is never formatted: citations stay as captured.
FORMATTING: dict[str, Rule] = {
    "address_zipOrPostcode": formatting.format_pin,
    "officialPhone": formatting.format_phone,
    "phone_numbers": formatting.format_phone,
    "email": formatting.format_email,
    "officialWebsite": formatting.format_url,
    "websites": formatting.format_url,
    "facebookLink": formatting.format_url,
}
