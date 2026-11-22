"""Facility state checked against the India Post pincode directory (#9).

Overrides spec #1's "never fills a value from another column or table" for
`address_state` only, and only when the PIN and the city together settle a conflict.

Three signals per Facility:
- A: the written state, only when it is an official state name.
- P: the directory states of the Facility's 6-digit PIN, ignoring `NA`.
- C: the state of the Facility's city: the directory states of districts whose
  name equals the city (case-insensitive), usable only when it is exactly one state.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_base import aliases

_STATE = "address_stateOrRegion"
_CITY = "address_city"
_PIN = "address_zipOrPostcode"

FLAGS = ["flag_state_corrected", "flag_pin_mismatch", "flag_address_conflict", "flag_pin_unverified"]

# Directory `statename` (any case) -> official name. `NA` is absent, so it maps to NULL.
_OFFICIAL_BY_KEY = {name.lower(): name for name in aliases.OFFICIAL_STATES}


def _official(state: Column) -> Column:
    """The official state name for a directory or Facility state, NULL when it is not one."""
    return F.create_map(*[F.lit(x) for pair in _OFFICIAL_BY_KEY.items() for x in pair])[F.lower(F.trim(state))]


def check_state(df: DataFrame, pincodes: DataFrame) -> DataFrame:
    """Correct `address_stateOrRegion` where PIN and city agree against it, and set the four flags.

    Runs on bronze column names, after state Spelling fixes and PIN formatting.
    `address_zipOrPostcode` is never changed.
    """
    offices = pincodes.select(
        F.col("pincode").cast("string").alias("pin"),
        F.lower(F.trim(F.col("district"))).alias("district_key"),
        _official(F.col("statename")).alias("directory_state"),
    )
    pin_states = offices.groupBy("pin").agg(
        F.array_distinct(F.collect_list("directory_state")).alias("_pin_states")
    )
    city_states = (
        offices.where(F.col("directory_state").isNotNull())
        .groupBy("district_key")
        .agg(F.array_distinct(F.collect_list("directory_state")).alias("_city_states"))
    )

    checked = (
        df.withColumns(
            {"_pin": F.when(F.col(_PIN).rlike(r"^[0-9]{6}$"), F.col(_PIN)), "_city_key": F.lower(F.col(_CITY))}
        )
        .join(F.broadcast(pin_states), F.col("_pin") == F.col("pin"), "left")
        .join(F.broadcast(city_states), F.col("_city_key") == F.col("district_key"), "left")
    )

    written = _official(F.col(_STATE))  # A
    pin_states_ = F.coalesce(F.col("_pin_states"), F.array().cast("array<string>"))  # P
    city_state = F.when(F.size(F.col("_city_states")) == 1, F.col("_city_states")[0])  # C
    conflict = written.isNotNull() & (F.size(pin_states_) > 0) & ~F.array_contains(pin_states_, written)
    outcome = (
        F.when(conflict & F.array_contains(pin_states_, city_state), "flag_state_corrected")
        .when(conflict & (city_state == written), "flag_pin_mismatch")
        .when(conflict, "flag_address_conflict")
        # A 6-digit PIN that is not in the directory, or only under `NA`.
        .when(written.isNotNull() & F.col("_pin").isNotNull() & (F.size(pin_states_) == 0), "flag_pin_unverified")
    )

    # The outcome is materialized before the state is replaced, so the flags never
    # see the corrected state.
    checked = checked.withColumns({"_outcome": outcome, "_city_state": city_state})
    return checked.withColumns(
        {
            _STATE: F.when(F.col("_outcome") == "flag_state_corrected", F.col("_city_state")).otherwise(
                F.col(_STATE)
            ),
            **{flag: F.coalesce(F.col("_outcome") == flag, F.lit(False)) for flag in FLAGS},
        }
    ).drop("_pin", "_city_key", "pin", "district_key", "_pin_states", "_city_states", "_outcome", "_city_state")
