"""Group D, description consistency (spec #13, #17).

`flag_desc_mentions_other_state` is true when `description` names an official
state other than `address_state`. Silver base's official state list is the
reference; aliases (`Orissa`, `Bombay`) and cities are not looked for. Which
state was named is never stored.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_base.aliases import OFFICIAL_STATES
from talaria.silver_facilities import words


def _state_pattern(state: str) -> str:
    """A regex for an official state name in lower-case text: whole words, `and` or `&`, no leading `The`."""
    parts = state.lower().removeprefix("the ").split()
    body = r"\s+".join(r"(?:and|&)" if part == "and" else rf"\Q{part}\E" for part in parts)
    return words.whole_words(body)


def add_columns(df: DataFrame) -> DataFrame:
    state, description = F.col("address_state"), F.lower(F.col("description"))
    other: Column = F.lit(False)
    for name in OFFICIAL_STATES:
        other = other | ((state != name) & description.rlike(_state_pattern(name)))
    flag = state.isin(OFFICIAL_STATES) & description.isNotNull() & other
    return df.withColumn("flag_desc_mentions_other_state", F.coalesce(flag, F.lit(False)))
