# Databricks notebook source
# MAGIC %md
# MAGIC # 08 · Facility districts
# MAGIC Links each facility to its NFHS-5 district (#44), so district health indicators can be joined to facilities.
# MAGIC By PIN through the India Post directory (the nearest post office when a PIN spans districts), else by city, else `unknown`.
# MAGIC Directory districts named differently in NFHS-5 go through `talaria/district_link/reference/district_aliases.csv`;
# MAGIC districts carved out since NFHS-5 link to their parent and are marked approximate.
# MAGIC Needs `07_silver_nfhs5` first. A failed runtime check stops the run before anything is written.

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.path.abspath(".."))
from config import BRONZE, SILVER, SILVER_FACILITY_DISTRICTS

from talaria.district_link import build_facility_districts
from talaria.district_link.checks import check_facility_districts
from talaria.district_link.link_counts import format_link_counts, link_counts

# COMMAND ----------

facilities = spark.table(SILVER["facilities"])
silver_nfhs5 = spark.table(SILVER["nfhs5"])
districts = build_facility_districts(facilities, spark.table(BRONZE["pincodes"]), silver_nfhs5).cache()

# COMMAND ----------

# Raises (and stops the run) on a lost or repeated facility, a district that isn't in
# Silver NFHS-5, an alias to a missing district, or a NULL district not marked unknown.
check_facility_districts(facilities, silver_nfhs5, districts)
print("Runtime checks passed")
print(format_link_counts(link_counts(districts)))

# COMMAND ----------

districts.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER_FACILITY_DISTRICTS)
print(f"-> {SILVER_FACILITY_DISTRICTS}: {spark.table(SILVER_FACILITY_DISTRICTS).count():,} rows")

# COMMAND ----------

display(spark.table(SILVER_FACILITY_DISTRICTS).where("district_link != 'pin'").limit(20))
