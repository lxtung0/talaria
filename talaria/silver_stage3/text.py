"""Shared definitions of #35 ("Shared definitions"): name patterns, NOISE, GENERIC
categories, list items and the categories free text names."""

import json

from pyspark.sql import Column
from pyspark.sql import functions as F

from talaria.silver_stage3.references import References

NAME_IS_HOSPITAL = r"hospital|medical college|aiims"
NAME_IS_CLINIC = (
    r"\bclinic\b|clinics\b|polyclinic|diagnostic|\blabs?\b|laborator|pathology|\bscans?\b|imaging"
    r"|dispensary|pharmacy|chemist"
)
CLINIC_TYPES = ["clinic", "dentist", "doctor", "pharmacy"]
# Text items about amenities, dropped before keyword matching.
NOISE = r"(?i)wheel ?-?chair|parking|bathroom|restroom|toilet|cafeteria|canteen|wifi"

GENERAL_MEDICINE = "Internal / Family / General Medicine"
OTHER = "Other / Unclassified"
# Ignored in the consistency checks only.
GENERIC = [GENERAL_MEDICINE, OTHER, "General Surgery", "Anesthesia", "Pathology & Laboratory", "Radiology & Imaging"]

TEXT_FIELDS = ["procedure", "equipment", "capability"]


def empty() -> Column:
    """An empty `array<string>`."""
    return F.array().cast("array<string>")


def lower_name_matches(pattern: str) -> Column:
    """`lower(name)` matches `pattern`; false when `name` is NULL."""
    return F.coalesce(F.lower(F.col("name")).rlike(pattern), F.lit(False))


def name_is_hospital() -> Column:
    return lower_name_matches(NAME_IS_HOSPITAL)


def name_is_clinic() -> Column:
    return lower_name_matches(NAME_IS_CLINIC)


def clinic_type() -> Column:
    return F.coalesce(F.col("facility_type").isin(CLINIC_TYPES), F.lit(False))


def items(column: Column) -> Column:
    """The non-blank items of a list column, as an array (empty, never NULL)."""
    return F.coalesce(F.filter(column, lambda item: item.isNotNull() & (F.trim(item) != "")), empty())


def without_noise(column: Column) -> Column:
    return F.filter(column, lambda item: ~item.rlike(NOISE))


def any_item_matches(column: Column, pattern: str) -> Column:
    return F.exists(column, lambda item: item.rlike(pattern))


def text_categories(column: Column, references: References) -> Column:
    """The categories whose `text_regex` matches at least one item of `column`."""
    return F.array_compact(
        F.array(
            *[
                F.when(any_item_matches(column, regex), F.lit(category))
                for category, regex in references.text_category_regex.items()
            ]
        )
    )


def literal_array(values: list[str]) -> Column:
    return F.array(*[F.lit(value) for value in values]) if values else empty()


def literal_map(mapping: dict, value_type: str) -> Column:
    """A Python dict as one literal Spark map (a single JSON string, not one argument per entry)."""
    return F.from_json(F.lit(json.dumps(mapping)), f"map<string,{value_type}>")


def supported(category: Column, found: Column, references: References) -> Column:
    """`category` or one of its related categories is in `found`."""
    related = F.coalesce(F.try_element_at(literal_map(references.related_categories, "array<string>"), category), empty())
    return F.array_contains(found, category) | F.exists(related, lambda other: F.array_contains(found, other))
