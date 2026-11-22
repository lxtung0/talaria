"""`gold_facility_items`: one row per claim (spec #37, "Table B")."""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.gold import columns

# A sentence ends at . ! or ? followed by whitespace, except after these abbreviations.
ABBREVIATIONS = [
    "Dr", "Mr", "Mrs", "Ms", "Pvt", "Ltd", "St", "No", "Co", "Inc",
    "Govt", "Hosp", "Ave", "Rd", "Sr", "Jr", "Prof",
]
# Java regex: the lookbehind keeps the punctuation in the sentence; (?i) also catches PVT. LTD.
SENTENCE_BREAK = r"(?i)(?<=[.!?])(?<!\b(?:" + "|".join(ABBREVIATIONS) + r")\.)\s+"


def description_sentences(description: Column) -> Column:
    """Trimmed, non-empty sentences; NULL description gives NULL (so no rows)."""
    pieces = F.transform(F.split(description, SENTENCE_BREAK), lambda piece: F.trim(piece))
    return F.filter(pieces, lambda piece: piece != "")


def build_items(silver: DataFrame) -> DataFrame:
    sources = [(F.col(name), item_type) for name, item_type in columns.LIST_ITEM_TYPES.items()]
    sources.append((description_sentences(F.col("description")), columns.DESCRIPTION_ITEM_TYPE))

    parts = []
    for items, item_type in sources:
        part = silver.select("unique_id", F.posexplode(items).alias("position", "item_text")).select(
            F.concat_ws(":", "unique_id", F.lit(item_type), F.col("position").cast("string")).alias("item_id"),
            "unique_id",
            F.lit(item_type).alias("item_type"),
            "item_text",
        )
        parts.append(part)

    items = parts[0]
    for part in parts[1:]:
        items = items.unionByName(part)
    return items.select(*columns.GOLD_FACILITY_ITEMS)
