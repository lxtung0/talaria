"""Group H, location flags (spec #13, #19).

Only Facilities with a Silver base location flag are checked; the flags are false
for every other Facility. Each flag names a problem, so false never confirms a
location. There is no "near the PIN" flag: ADR 0001 notes that coordinates
appear geocoded from the PIN, so being near proves nothing.

Distances and centroids are working columns only and never leave the function.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_base.state_check import FLAGS as SILVER_BASE_LOCATION_FLAGS

FLAGS = ["flag_coords_far_from_written_pin", "flag_no_same_prefix_pin_nearby", "flag_coords_shared"]

# A Facility farther than this from its written PIN's centroid is far. A fixed
# distance, not the PIN's radius: the directory has offices with coordinates
# hundreds of km off, and one of them inflated the radius enough to hide far
# Facilities (7 of 31 on the 2026-11-22 data).
_FAR_KM = 10.0
# A same-prefix PIN counts as nearby within this distance.
_NEARBY_KM = 5.0
# Directory offices outside India's bounding box are skipped.
_INDIA_LAT = (6.0, 37.6)
_INDIA_LON = (68.0, 97.6)

_PIN_SHAPE = r"^[0-9]{6}$"


def add_columns(df: DataFrame, pincodes: DataFrame) -> DataFrame:
    pins = _pin_centroids(pincodes)

    in_scope = F.lit(False)
    for name in SILVER_BASE_LOCATION_FLAGS:
        in_scope = in_scope | F.col(name)
    has_coordinates = F.col("latitude").isNotNull() & F.col("longitude").isNotNull()

    scoped = df.where(in_scope & has_coordinates).select(
        F.col("unique_id").alias("_h_id"),
        F.col("latitude").alias("_h_lat"),
        F.col("longitude").alias("_h_lon"),
        F.when(F.col("address_pincode").rlike(_PIN_SHAPE), F.col("address_pincode")).alias("_h_pin"),
    )

    far = (
        scoped.join(F.broadcast(pins), F.col("_h_pin") == F.col("_p_pin"))
        .where(
            _haversine_km(F.col("_h_lat"), F.col("_h_lon"), F.col("_p_lat"), F.col("_p_lon"))
            > _FAR_KM
        )
        .select(F.col("_h_id").alias("_far_id"))
    )

    # Joined on the 3-digit prefix, so only PINs in the same postal region are compared.
    with_same_prefix_nearby = (
        scoped.where(F.col("_h_pin").isNotNull())
        .join(F.broadcast(pins), F.substring(F.col("_h_pin"), 1, 3) == F.substring(F.col("_p_pin"), 1, 3))
        .where(_haversine_km(F.col("_h_lat"), F.col("_h_lon"), F.col("_p_lat"), F.col("_p_lon")) <= _NEARBY_KM)
        .select("_h_id")
        .distinct()
    )
    no_same_prefix = (
        scoped.where(F.col("_h_pin").isNotNull())
        .join(with_same_prefix_nearby, "_h_id", "left_anti")
        .select(F.col("_h_id").alias("_lonely_id"))
    )

    # Shared with any other Facility in the table, flagged or not.
    shared_coordinates = (
        df.where(has_coordinates)
        .groupBy("latitude", "longitude")
        .count()
        .where(F.col("count") > 1)
        .select(F.col("latitude").alias("_s_lat"), F.col("longitude").alias("_s_lon"))
    )
    shared = scoped.join(
        shared_coordinates, (F.col("_h_lat") == F.col("_s_lat")) & (F.col("_h_lon") == F.col("_s_lon"))
    ).select(F.col("_h_id").alias("_shared_id"))

    return (
        df.join(far, F.col("unique_id") == F.col("_far_id"), "left")
        .join(no_same_prefix, F.col("unique_id") == F.col("_lonely_id"), "left")
        .join(shared, F.col("unique_id") == F.col("_shared_id"), "left")
        .withColumns(
            {
                "flag_coords_far_from_written_pin": F.col("_far_id").isNotNull(),
                "flag_no_same_prefix_pin_nearby": F.col("_lonely_id").isNotNull(),
                "flag_coords_shared": F.col("_shared_id").isNotNull(),
            }
        )
        .drop("_far_id", "_lonely_id", "_shared_id")
    )


def _pin_centroids(pincodes: DataFrame) -> DataFrame:
    """One row per PIN: the median latitude and longitude of its offices.

    The median, not the mean, so a minority of offices with wrong coordinates
    can't drag the centroid.

    Coordinates are text in the source, with `NA` among them: `try_cast` skips
    those instead of raising under ANSI mode.
    """
    offices = pincodes.select(
        F.col("pincode").cast("string").alias("_p_pin"),
        F.expr("try_cast(latitude AS double)").alias("_o_lat"),
        F.expr("try_cast(longitude AS double)").alias("_o_lon"),
    ).where(F.col("_o_lat").between(*_INDIA_LAT) & F.col("_o_lon").between(*_INDIA_LON))

    return offices.groupBy("_p_pin").agg(
        F.expr("percentile(_o_lat, 0.5)").alias("_p_lat"),
        F.expr("percentile(_o_lon, 0.5)").alias("_p_lon"),
    )


def _haversine_km(lat1: Column, lon1: Column, lat2: Column, lon2: Column) -> Column:
    """Great-circle distance in kilometres."""
    d_lat = F.radians(lat2 - lat1)
    d_lon = F.radians(lon2 - lon1)
    a = F.sin(d_lat / 2) ** 2 + F.cos(F.radians(lat1)) * F.cos(F.radians(lat2)) * F.sin(d_lon / 2) ** 2
    return F.lit(2 * 6371.0) * F.asin(F.least(F.lit(1.0), F.sqrt(a)))
