"""Group G, page update date (spec #13): reads the text and creates no date column."""

import datetime

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

_VALUE = "recency_of_page_update"
# The shape is checked first because a cast to date also accepts `2025` and `2025-10`.
_ISO_SHAPE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"


def add_columns(df: DataFrame, run_date: datetime.date) -> DataFrame:
    value = F.col(_VALUE)
    # try_cast, because `to_date` raises on `2025-13-40` under ANSI mode (the Databricks default).
    date = F.when(value.rlike(_ISO_SHAPE), F.expr(f"try_cast({_VALUE} AS date)"))
    return df.withColumns(
        {
            "flag_page_update_unparsable": value.isNotNull() & date.isNull(),
            "flag_future_page_update": F.coalesce(date > F.lit(run_date), F.lit(False)),
        }
    )
