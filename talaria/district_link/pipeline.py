"""The district link pipeline (#44): directory district -> NFHS district, then
facility -> directory district by PIN, then by city, else unknown."""

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

from talaria.district_link.aliases import DistrictAlias, load_aliases
from talaria.silver_base import spelling

# `district_link` values.
PIN = "pin"  # every post office of the PIN is in one NFHS district
PIN_NEAREST_OFFICE = "pin_nearest_office"  # the PIN spans districts: the office nearest the facility
PIN_MOST_OFFICES = "pin_most_offices"  # ... and no coordinates to compare: the district with most offices
CITY = "city"  # not linked by PIN: the facility's city names a district of its state
CITY_MAJORITY = "city_majority"  # ... or most PIN-linked facilities of its city and state share one district
UNKNOWN = "unknown"
LINKS = [PIN, PIN_NEAREST_OFFICE, PIN_MOST_OFFICES, CITY, CITY_MAJORITY, UNKNOWN]

OUTPUT_COLUMNS = ["unique_id", "nfhs_state", "nfhs_district", "district_link", "district_approximate"]

# A city's PIN-linked facilities vouch for its district only when they agree this much.
CITY_MAJORITY_SHARE = 0.8
CITY_MAJORITY_MIN_FACILITIES = 3

EARTH_RADIUS_KM = 6371.0
NUMBER = r"^-?\d+(\.\d+)?$"


def district_key(name: Column) -> Column:
    """Letters only, lower case: `North & Middle Andaman` and `NORTH AND MIDDLE ANDAMAN` differ, by design."""
    return F.regexp_replace(F.lower(name), r"[^a-z]", "")


def _coordinate(value: Column) -> Column:
    text = F.trim(value.cast("string"))
    return F.when(text.rlike(NUMBER), text.cast("double"))


def _distance_km(lat1: Column, lon1: Column, lat2: Column, lon2: Column) -> Column:
    """Great-circle distance; NULL when any coordinate is."""
    phi1, phi2 = F.radians(lat1), F.radians(lat2)
    half_dphi, half_dlambda = F.radians(lat2 - lat1) / 2, F.radians(lon2 - lon1) / 2
    a = F.sin(half_dphi) ** 2 + F.cos(phi1) * F.cos(phi2) * F.sin(half_dlambda) ** 2
    return 2 * EARTH_RADIUS_KM * F.asin(F.sqrt(a))


def _nfhs_districts(silver_nfhs5: DataFrame) -> DataFrame:
    return silver_nfhs5.select(
        F.col("state_ut").alias("nfhs_state"),
        F.col("district_name").alias("nfhs_district"),
        district_key(F.col("district_name")).alias("_nfhs_key"),
    )


def _alias_table(silver_nfhs5: DataFrame, aliases: list[DistrictAlias]) -> DataFrame:
    rows = [(a.state, a.directory_district, a.nfhs_district, a.approximate) for a in aliases]
    schema = "state string, directory_district string, alias_district string, alias_approximate boolean"
    return silver_nfhs5.sparkSession.createDataFrame(rows, schema).select(
        "state", district_key(F.col("directory_district")).alias("key"), "alias_district", "alias_approximate"
    )


def _resolved(names: DataFrame, nfhs: DataFrame, alias_table: DataFrame) -> DataFrame:
    """`names` (`state`, `key`) with the NFHS district they name: directly, else through an alias."""
    direct = nfhs.select(
        F.col("nfhs_state").alias("state"), F.col("_nfhs_key").alias("key"), F.col("nfhs_district").alias("direct")
    )
    return (
        names.join(direct, ["state", "key"], "left")
        .join(alias_table, ["state", "key"], "left")
        .select(
            "*",
            F.when(F.col("direct").isNotNull(), F.col("state")).when(F.col("alias_district").isNotNull(), F.col("state")).alias("nfhs_state"),
            F.coalesce("direct", "alias_district").alias("nfhs_district"),
            F.when(F.col("direct").isNotNull(), F.lit(False))
            .otherwise(F.coalesce("alias_approximate", F.lit(False)))
            .alias("approximate"),
        )
        .drop("direct", "alias_district", "alias_approximate")
    )


def _offices(pincodes: DataFrame, nfhs: DataFrame, alias_table: DataFrame) -> DataFrame:
    """Post offices with a PIN and the NFHS district their directory district names."""
    offices = pincodes.select(
        F.trim(F.col("pincode").cast("string")).alias("pin"),
        spelling.official_state(F.col("statename")).alias("state"),
        district_key(F.col("district")).alias("key"),
        _coordinate(F.col("latitude")).alias("office_lat"),
        _coordinate(F.col("longitude")).alias("office_lon"),
    ).where(F.col("pin").isNotNull())
    return _resolved(offices, nfhs, alias_table).where(F.col("nfhs_district").isNotNull())


def _pin_links(facilities: DataFrame, offices: DataFrame) -> DataFrame:
    """Facilities whose PIN reaches an NFHS district: one row each."""
    candidates = facilities.join(offices, "pin").withColumn(
        "_km", _distance_km(F.col("latitude"), F.col("longitude"), F.col("office_lat"), F.col("office_lon"))
    )
    by_facility = Window.partitionBy("unique_id")
    district = F.struct("nfhs_state", "nfhs_district")
    candidates = candidates.withColumn("_districts", F.size(F.collect_set(district).over(by_facility)))

    nearest = candidates.withColumn(
        "_rank", F.row_number().over(by_facility.orderBy(F.col("_km").asc_nulls_last(), "nfhs_state", "nfhs_district"))
    ).where("_rank = 1")

    most = (
        candidates.groupBy("unique_id", "nfhs_state", "nfhs_district")
        .agg(F.count(F.lit(1)).alias("_offices"), F.max(F.col("approximate").cast("int")).alias("_approx"))
        .withColumn("_rank", F.row_number().over(by_facility.orderBy(F.desc("_offices"), "nfhs_state", "nfhs_district")))
        .where("_rank = 1")
        .select("unique_id", F.col("nfhs_state").alias("most_state"), F.col("nfhs_district").alias("most_district"), "_approx")
    )

    one = F.col("_districts") == 1
    by_distance = F.col("_km").isNotNull()
    return nearest.join(most, "unique_id").select(
        "unique_id",
        F.when(one | by_distance, F.col("nfhs_state")).otherwise(F.col("most_state")).alias("nfhs_state"),
        F.when(one | by_distance, F.col("nfhs_district")).otherwise(F.col("most_district")).alias("nfhs_district"),
        F.when(one, F.lit(PIN)).when(by_distance, F.lit(PIN_NEAREST_OFFICE)).otherwise(F.lit(PIN_MOST_OFFICES)).alias("district_link"),
        F.when(one, F.col("_approx") == 1)
        .when(by_distance, F.col("approximate"))
        .otherwise(F.lit(True))
        .alias("district_approximate"),
    )


def _city_links(facilities: DataFrame, nfhs: DataFrame, alias_table: DataFrame) -> DataFrame:
    """Facilities whose city names an NFHS district of their state, directly or through an alias."""
    cities = facilities.select("unique_id", F.col("address_state").alias("state"), district_key(F.col("address_city")).alias("key"))
    return (
        _resolved(cities.where(F.col("key") != ""), nfhs, alias_table)
        .where(F.col("nfhs_district").isNotNull())
        .select("unique_id", "nfhs_state", "nfhs_district", F.lit(CITY).alias("district_link"), F.col("approximate").alias("district_approximate"))
    )


def _city_majority_links(rest: DataFrame, people: DataFrame, by_pin: DataFrame) -> DataFrame:
    """Facilities whose city (in the same state) has at least `CITY_MAJORITY_MIN_FACILITIES`
    PIN-linked facilities, `CITY_MAJORITY_SHARE` of them in one district: that district, approximate.

    Covers cities whose name isn't a district name (`Bengaluru` is in NFHS-5's `Bangalore`).
    """
    place = [F.col("address_state").alias("state"), district_key(F.col("address_city")).alias("key")]
    linked = people.select("unique_id", *place).join(by_pin, "unique_id")
    per_district = linked.groupBy("state", "key", "nfhs_state", "nfhs_district").agg(F.count(F.lit(1)).alias("n"))
    city = Window.partitionBy("state", "key")
    majority = (
        per_district.withColumn("total", F.sum("n").over(city))
        .withColumn("_rank", F.row_number().over(city.orderBy(F.desc("n"), "nfhs_state", "nfhs_district")))
        .where(
            (F.col("_rank") == 1)
            & (F.col("total") >= CITY_MAJORITY_MIN_FACILITIES)
            & (F.col("n") >= CITY_MAJORITY_SHARE * F.col("total"))
        )
    )
    return (
        rest.select("unique_id", *place)
        .where(F.col("key") != "")
        .join(majority, ["state", "key"])
        .select("unique_id", "nfhs_state", "nfhs_district", F.lit(CITY_MAJORITY).alias("district_link"), F.lit(True).alias("district_approximate"))
    )


def build_facility_districts(
    facilities: DataFrame, pincodes: DataFrame, silver_nfhs5: DataFrame, aliases: list[DistrictAlias] | None = None
) -> DataFrame:
    """One row per facility of `facilities` (Silver facilities or later): its NFHS-5 district and how it was found.

    `pincodes` is the bronze pincode directory; `aliases` defaults to the repo's alias CSV.
    """
    aliases = load_aliases() if aliases is None else aliases
    nfhs = _nfhs_districts(silver_nfhs5)
    alias_table = _alias_table(silver_nfhs5, aliases)
    people = facilities.select(
        "unique_id",
        F.trim(F.col("address_pincode").cast("string")).alias("pin"),
        "address_city",
        "address_state",
        _coordinate(F.col("latitude")).alias("latitude"),
        _coordinate(F.col("longitude")).alias("longitude"),
    )

    by_pin = _pin_links(people.where(F.col("pin").isNotNull()), _offices(pincodes, nfhs, alias_table))
    rest = people.join(by_pin.select("unique_id"), "unique_id", "left_anti")
    by_city = _city_links(rest, nfhs, alias_table)
    rest = rest.join(by_city.select("unique_id"), "unique_id", "left_anti")
    by_majority = _city_majority_links(rest, people, by_pin)
    linked = by_pin.unionByName(by_city).unionByName(by_majority)

    return (
        people.select("unique_id")
        .join(linked, "unique_id", "left")
        .select(
            "unique_id",
            "nfhs_state",
            "nfhs_district",
            F.coalesce("district_link", F.lit(UNKNOWN)).alias("district_link"),
            F.coalesce("district_approximate", F.lit(False)).alias("district_approximate"),
        )
    )
