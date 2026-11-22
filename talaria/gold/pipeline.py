"""The Gold pipeline: score each Facility and explode its claims (spec #37)."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.gold import columns, items, scoring


def build_gold(silver_stage3: DataFrame) -> tuple[DataFrame, DataFrame]:
    """`(gold_facilities, gold_facility_items)` from Silver Stage 3.

    Copied columns are verbatim; only the score, its log and `location_uncertain` are new.
    Veterinary facilities are left out of both tables.
    """
    silver_stage3 = columns.in_scope(silver_stage3)
    location_uncertain = F.lit(False)
    for name in columns.LOCATION_FLAGS:
        location_uncertain = location_uncertain | F.coalesce(F.col(name), F.lit(False))

    facilities = silver_stage3.select(
        *columns.COPIED_COLUMNS,
        *[column.alias(name) for name, column in scoring.score_columns().items()],
        location_uncertain.alias("location_uncertain"),
        "needs_investigation",
    ).select(*columns.GOLD_FACILITIES)
    return facilities, items.build_items(silver_stage3)
