"""The Silver facilities pipeline: one step per flag group of spec #13.

To add a group: write its `add_columns` in its own module, call it in
`build_silver_facilities`, and list its columns in `columns.NEW_COLUMNS`.
"""

import datetime

from pyspark.sql import DataFrame

from talaria.silver_facilities import affiliation, columns, page_dates


def build_silver_facilities(
    silver_base: DataFrame, bronze: DataFrame, pincodes: DataFrame, run_date: datetime.date
) -> DataFrame:
    """Silver base with every column unchanged, plus `columns.NEW_COLUMNS`.

    `bronze` is the bronze facilities snapshot (group E counts raw affiliations),
    `pincodes` the bronze pincode directory (group H), and `run_date` the day a
    page date must be after to count as in the future.
    """
    df = silver_base
    df = affiliation.add_columns(df, bronze)
    df = page_dates.add_columns(df, run_date)
    # Only listed columns leave the function, so a group's working columns are never stored.
    return df.select(*silver_base.columns, *[column.name for column in columns.NEW_COLUMNS])
