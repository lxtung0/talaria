"""Group A, contact consistency (spec #13): official contacts against the Facility's own lists."""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_base.formatting import url_host


def add_columns(df: DataFrame) -> DataFrame:
    phones, websites = F.col("phone_numbers"), F.col("websites")
    return df.withColumns(
        {
            "flag_official_phone_not_in_list": _not_in_list(
                _last_10_digits(F.col("official_phone")), F.transform(phones, _last_10_digits)
            ),
            "flag_phone_list_without_official": (
                F.col("official_phone").isNull() & F.coalesce(F.size(phones) > 0, F.lit(False))
            ),
            "flag_official_website_not_in_list": _not_in_list(
                url_host(F.col("official_website")), F.transform(websites, url_host)
            ),
        }
    )


def _last_10_digits(phone: Column) -> Column:
    """Every digit when there are fewer than 10; empty when there are none."""
    return F.regexp_extract(F.regexp_replace(phone, "[^0-9]", ""), "([0-9]{0,10})$", 1)


def _not_in_list(value: Column, items: Column) -> Column:
    """True when there is a value and no item equals it, a NULL list included (spec #13).

    False when there is nothing to compare: the value is NULL or empty.
    """
    has_value = F.coalesce(value != "", F.lit(False))
    return has_value & ~F.coalesce(F.array_contains(items, value), F.lit(False))
