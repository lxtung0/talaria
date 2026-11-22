"""District link runtime checks (#44). Run by the notebook on live data, before anything is written."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.district_link import pipeline
from talaria.district_link.aliases import DistrictAlias, load_aliases


def check_facility_districts(
    facilities: DataFrame, silver_nfhs5: DataFrame, districts: DataFrame, aliases: list[DistrictAlias] | None = None
) -> None:
    """Raise ValueError naming every failed check; return quietly when all pass.

    - The columns are `pipeline.OUTPUT_COLUMNS`; one row per facility.
    - `nfhs_district` is NULL exactly when `district_link` is `unknown`; links are known values.
    - Every linked district is a Silver NFHS-5 district, and so is every alias target.
    """
    aliases = load_aliases() if aliases is None else aliases
    if districts.columns != pipeline.OUTPUT_COLUMNS:
        _fail([f"columns are {districts.columns}, expected {pipeline.OUTPUT_COLUMNS}"])

    district, link = F.col("nfhs_district"), F.col("district_link")
    counts = districts.agg(
        F.count(F.lit(1)).alias("rows"),
        F.countDistinct("unique_id").alias("ids"),
        F.count(F.when(district.isNull() != (link == pipeline.UNKNOWN), 1)).alias("mismatch"),
        F.count(F.when(~link.isin(pipeline.LINKS) | link.isNull(), 1)).alias("bad_link"),
        F.count(F.when(F.col("district_approximate").isNull(), 1)).alias("null_approx"),
    ).first()
    failures = []
    facility_rows = facilities.count()
    if counts.rows != facility_rows or counts.ids != facility_rows:
        failures.append(f"{counts.rows} rows for {counts.ids} ids, facilities has {facility_rows}")
    if counts.mismatch:
        failures.append(f"nfhs_district: {counts.mismatch} row(s) NULL without 'unknown', or linked with 'unknown'")
    if counts.bad_link:
        failures.append(f"district_link: {counts.bad_link} row(s) not one of {pipeline.LINKS}")
    if counts.null_approx:
        failures.append(f"district_approximate: {counts.null_approx} row(s) NULL")

    nfhs = silver_nfhs5.select(F.col("state_ut").alias("nfhs_state"), F.col("district_name").alias("nfhs_district"))
    stray = districts.where(district.isNotNull()).join(nfhs, ["nfhs_state", "nfhs_district"], "left_anti").count()
    if stray:
        failures.append(f"{stray} facilities linked to a district that isn't in Silver NFHS-5")
    known = {(row.nfhs_state, row.nfhs_district) for row in nfhs.collect()}
    missing = [f"{a.state} / {a.nfhs_district}" for a in aliases if a.nfhs_district and (a.state, a.nfhs_district) not in known]
    if missing:
        failures.append(f"alias targets not in Silver NFHS-5: {missing}")
    if failures:
        _fail(failures)


def _fail(failures: list[str]) -> None:
    raise ValueError("District link runtime checks failed:\n- " + "\n- ".join(failures))
