"""Unpack the source Facilities table into the two app tables (ticket #27).

`build_app_tables(facilities, gold=None) -> (app_facilities, app_facility_items)`:
no reads, writes or Databricks-only calls, so it runs on local Spark. The notebook
adds `h3_r5` afterwards, since H3 functions only exist on Databricks.

`facilities` (Silver) supplies the claim lists and flags. `gold`, when given,
supplies the confidence: only Facilities in Gold are kept (it leaves out
veterinary ones), with its `confidence_score` and `confidence_reasons` log.
Gold itself is too narrow to replace Silver here: it has no claim lists or flags.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

# The columns the app shows, besides every `flag_*` column.
SHOWN_COLUMNS = [
    "unique_id", "name", "facility_type",
    "address_line1", "address_line2", "address_line3", "address_city", "address_state", "address_pincode",
    "latitude", "longitude", "official_phone", "official_website", "source_urls",
]
QUALITY_COLUMNS = ["needs_investigation", "truncated_columns"]
PLACEHOLDER_CONFIDENCE = 0.5

# Each list column, the `item_type` its items get and the letter in their `item_id`.
LIST_ITEMS = [
    ("specialties", "specialty", "s"),
    ("procedure", "procedure", "p"),
    ("equipment", "equipment", "e"),
    ("capability", "capability", "c"),
]
DESCRIPTION_TYPE, DESCRIPTION_LETTER = "description_sentence", "d"
ITEM_TYPES = [item_type for _, item_type, _ in LIST_ITEMS] + [DESCRIPTION_TYPE]

# A sentence ends at `.`, `!` or `?` followed by whitespace; the mark stays with
# its sentence, so each sentence is a verbatim slice of the description.
SENTENCE_BREAK = r"(?<=[.!?])\s+"


def build_app_tables(facilities: DataFrame, gold: DataFrame | None = None) -> tuple[DataFrame, DataFrame]:
    """`app_facilities` (one row per Facility) and `app_facility_items` (one row per claim)."""
    if gold is not None:
        scores = gold.select("unique_id", "confidence_score", "confidence_reasons")
        facilities = facilities.drop("confidence_score", "confidence_reasons").join(scores, "unique_id")
    return _app_facilities(facilities), _app_facility_items(facilities)


def _app_facilities(facilities: DataFrame) -> DataFrame:
    flags = [c for c in facilities.columns if c.startswith("flag_")]
    confidence = (
        F.col("confidence_score").cast("double")
        if "confidence_score" in facilities.columns
        else F.lit(PLACEHOLDER_CONFIDENCE)
    )
    reasons = (
        F.col("confidence_reasons")
        if "confidence_reasons" in facilities.columns
        else F.lit(None).cast("array<string>")
    )
    return facilities.select(
        *SHOWN_COLUMNS, *flags, *QUALITY_COLUMNS, confidence.alias("confidence_score"), reasons.alias("confidence_reasons")
    )


def _app_facility_items(facilities: DataFrame) -> DataFrame:
    parts = [
        _items(facilities, F.col(column), item_type, letter) for column, item_type, letter in LIST_ITEMS
    ]
    parts.append(
        _items(facilities, F.split("description", SENTENCE_BREAK), DESCRIPTION_TYPE, DESCRIPTION_LETTER, trim=True)
    )
    items = parts[0]
    for part in parts[1:]:
        items = items.unionByName(part)
    return items


def _items(facilities: DataFrame, values, item_type: str, letter: str, trim: bool = False) -> DataFrame:
    """One row per non-empty value; `item_id` is `<unique_id>-<letter><position>`.

    List items are kept exactly as stored. Description sentences are only
    trimmed of the whitespace around the break, which is not part of either sentence.
    """
    exploded = facilities.select("unique_id", F.posexplode_outer(values).alias("position", "item_text"))
    if trim:
        exploded = exploded.withColumn("item_text", F.trim("item_text"))
    return exploded.where(F.col("item_text").isNotNull() & (F.trim("item_text") != "")).select(
        F.concat_ws("-", "unique_id", F.concat(F.lit(letter), F.col("position").cast("string"))).alias("item_id"),
        "unique_id",
        F.lit(item_type).alias("item_type"),
        "item_text",
    )
