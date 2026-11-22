"""The two Gold schemas (spec #37), a contract with the care-finder app (#26).

The pipeline selects these columns in this order and the runtime checks compare
the output types against them, so a schema change is one edit here.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.silver_facilities import location

# Copied verbatim from Silver Stage 3, in output order.
COPIED_COLUMNS = {
    "unique_id": "string",
    "name": "string",
    "facility_type": "string",
    "address_city": "string",
    "address_state": "string",
    "address_pincode": "string",
    "latitude": "double",
    "longitude": "double",
    "official_phone": "string",
    "official_website": "string",
    "source_urls": "array<string>",
}

GOLD_FACILITIES = COPIED_COLUMNS | {
    "confidence_score": "double",
    "confidence_reasons": "array<string>",
    "location_uncertain": "boolean",
    "needs_investigation": "boolean",
}

GOLD_FACILITY_ITEMS = {
    "item_id": "string",
    "unique_id": "string",
    "item_type": "string",
    "item_text": "string",
}

# Silver list column -> item_type. `description` is split into sentences instead.
LIST_ITEM_TYPES = {
    "specialties": "specialty",
    "procedure": "procedure",
    "equipment": "equipment",
    "capability": "capability",
}
DESCRIPTION_ITEM_TYPE = "description_sentence"
ITEM_TYPES = [*LIST_ITEM_TYPES.values(), DESCRIPTION_ITEM_TYPE]

def in_scope(silver: DataFrame) -> DataFrame:
    """Gold covers human healthcare only: Stage 3's veterinary facilities (R1) are left out."""
    return silver.where(~F.coalesce(F.col("is_veterinary"), F.lit(False)))


# `location_uncertain` is true when any group H flag is true.
LOCATION_FLAGS = location.FLAGS
