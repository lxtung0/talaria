"""Facility state checked against the India Post pincode directory (#9, ADR 0001).

Overrides spec #1's "never fills a value from another column or table" for
`address_state` only, and only when the PIN and the city together settle a conflict.

Three signals per Facility:
- written state: `address_state`, only when it is an official state name.
- PIN states: the directory states of the Facility's 6-digit PIN, ignoring `NA`.
- city state: the directory states of districts whose name equals the city
  (case-insensitive), usable only when it is exactly one state.
Coordinates are not a signal: they appear geocoded from the PIN.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.silver_base.spelling import official_state

_STATE = "address_stateOrRegion"
_CITY = "address_city"
_PIN = "address_zipOrPostcode"

FLAGS = ["flag_state_corrected", "flag_pin_mismatch", "flag_address_conflict", "flag_pin_unverified"]


def check_state(df: DataFrame, pincodes: DataFrame) -> DataFrame:
    """Correct `address_stateOrRegion` where PIN and city agree against it, and set the four flags.

    Runs on bronze column names, after state Spelling fixes and PIN formatting.
    `address_zipOrPostcode` is never changed.
    """
    offices = pincodes.select(
        F.col("pincode").cast("string").alias("pin"),
        F.lower(F.trim(F.col("district"))).alias("district_key"),
        official_state(F.col("statename")).alias("directory_state"),
    )
    states_by_pin = offices.groupBy("pin").agg(
        F.array_distinct(F.collect_list("directory_state")).alias("_pin_states")
    )
    states_by_district = (
        offices.where(F.col("directory_state").isNotNull())
        .groupBy("district_key")
        .agg(F.array_distinct(F.collect_list("directory_state")).alias("_city_states"))
    )

    checked = (
        df.withColumns(
            {"_pin": F.when(F.col(_PIN).rlike(r"^[0-9]{6}$"), F.col(_PIN)), "_city_key": F.lower(F.col(_CITY))}
        )
        .join(F.broadcast(states_by_pin), F.col("_pin") == F.col("pin"), "left")
        .join(F.broadcast(states_by_district), F.col("_city_key") == F.col("district_key"), "left")
    )

    written_state = official_state(F.col(_STATE))
    pin_states = F.coalesce(F.col("_pin_states"), F.array().cast("array<string>"))
    city_state = F.when(F.size(F.col("_city_states")) == 1, F.col("_city_states")[0])
    conflict = written_state.isNotNull() & (F.size(pin_states) > 0) & ~F.array_contains(pin_states, written_state)
    outcome = (
        F.when(conflict & F.array_contains(pin_states, city_state), "flag_state_corrected")
        .when(conflict & (city_state == written_state), "flag_pin_mismatch")
        .when(conflict, "flag_address_conflict")
        # A 6-digit PIN that is not in the directory, or only under `NA`.
        .when(
            written_state.isNotNull() & F.col("_pin").isNotNull() & (F.size(pin_states) == 0), "flag_pin_unverified"
        )
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
