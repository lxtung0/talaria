# Databricks notebook source
# MAGIC %md
# MAGIC # 09 · Gold district cells
# MAGIC Maps every H3 res-5 cell with post offices to an NFHS-5 district, with the district indicators the care finder shows,
# MAGIC so the app can look up the area around the location a user enters by its cell (the same cells as its search).
# MAGIC Each post office gets its NFHS-5 district through the district link's aliases (#44); a cell takes the district most of its offices are in.
# MAGIC Needs `07_silver_nfhs5` first. A failed runtime check stops the run before anything is written.

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.path.abspath(".."))
from config import BRONZE, GOLD, SILVER

from pyspark.sql import functions as F

from talaria.district_link import office_districts
from talaria.gold_districts import build_district_cells
from talaria.gold_districts.checks import check_district_cells

# COMMAND ----------

silver_nfhs5 = spark.table(SILVER["nfhs5"])
offices = office_districts(spark.table(BRONZE["pincodes"]), silver_nfhs5)
# H3 functions only exist on Databricks, so the cell is added here, not in the package.
offices = offices.withColumn("h3_r5", F.expr("h3_longlatash3string(office_lon, office_lat, 5)"))
cells = build_district_cells(offices, silver_nfhs5).cache()

# COMMAND ----------

# Raises (and stops the run) on a repeated or NULL cell, a district that isn't in
# Silver NFHS-5, or a district share outside (0, 1].
check_district_cells(silver_nfhs5, cells)
print("Runtime checks passed")
display(
    cells.agg(
        F.count(F.lit(1)).alias("cells"),
        F.countDistinct("nfhs_state", "nfhs_district").alias("districts"),
        F.count(F.when(F.col("district_share") < 1, 1)).alias("border_cells"),
        F.count(F.when(F.col("district_approximate"), 1)).alias("approximate_cells"),
        F.count(F.when(F.col("insurance_pct").isNull(), 1)).alias("insurance_null"),
        F.count(F.when(F.col("insurance_pct_low_sample"), 1)).alias("insurance_low_sample"),
    )
)

# COMMAND ----------

cells.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(GOLD["district_cells"])
print(f"-> {GOLD['district_cells']}: {spark.table(GOLD['district_cells']).count():,} rows")

# COMMAND ----------

display(spark.table(GOLD["district_cells"]).where("district_share < 1").limit(20))
