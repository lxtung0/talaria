"""Gold district cells runtime checks. Run by the notebook on live data, before anything is written."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from talaria.gold_districts import pipeline


def check_district_cells(silver_nfhs5: DataFrame, cells: DataFrame) -> None:
    """Raise ValueError naming every failed check; return quietly when all pass.

    - The columns are `pipeline.OUTPUT_COLUMNS`; `h3_r5` is non-null and unique.
    - Every district is a Silver NFHS-5 district; `district_share` is in (0, 1].
    """
    if cells.columns != pipeline.OUTPUT_COLUMNS:
        _fail([f"columns are {cells.columns}, expected {pipeline.OUTPUT_COLUMNS}"])

    share = F.col("district_share")
    counts = cells.agg(
        F.count(F.lit(1)).alias("rows"),
        F.countDistinct("h3_r5").alias("cells"),
        F.count(F.when(F.col("h3_r5").isNull(), 1)).alias("null_cell"),
        F.count(F.when(share.isNull() | (share <= 0) | (share > 1), 1)).alias("bad_share"),
    ).first()
    nfhs = silver_nfhs5.select(F.col("state_ut").alias("nfhs_state"), F.col("district_name").alias("nfhs_district"))
    stray = cells.join(nfhs, ["nfhs_state", "nfhs_district"], "left_anti").count()

    failures = []
    if counts.null_cell:
        failures.append(f"h3_r5: {counts.null_cell} row(s) NULL")
    if counts.cells != counts.rows - counts.null_cell:
        failures.append(f"h3_r5 is repeated: {counts.rows} rows for {counts.cells} cells")
    if counts.bad_share:
        failures.append(f"district_share: {counts.bad_share} row(s) NULL or outside (0, 1]")
    if stray:
        failures.append(f"{stray} cell(s) with a district that isn't in Silver NFHS-5")
    if failures:
        _fail(failures)


def _fail(failures: list[str]) -> None:
    raise ValueError("Gold district cells runtime checks failed:\n- " + "\n- ".join(failures))
