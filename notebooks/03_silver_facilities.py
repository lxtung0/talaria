# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Silver facilities
# MAGIC Builds the second and final Silver stage for facilities (spec #13): Silver base, unchanged, plus new flag and value columns.
# MAGIC Reads Silver base, bronze facilities and the bronze pincode directory, runs `build_silver_facilities`, checks the result,
# MAGIC prints true/false counts per flag, then overwrites the Silver facilities table.
# MAGIC A failed runtime check stops the run before anything is written.

# COMMAND ----------

import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(".."))
from config import BRONZE, SILVER, SILVER_BASE

from talaria.silver_facilities import build_silver_facilities
from talaria.silver_facilities.checks import check_silver_facilities
from talaria.silver_facilities.flag_counts import flag_counts, format_flag_counts

# COMMAND ----------

silver_base = spark.table(SILVER_BASE["facilities"])
bronze = spark.table(BRONZE["facilities"])
pincodes = spark.table(BRONZE["pincodes"])
# A page date after this day is in the future. Set it by hand to reproduce an earlier run.
run_date = datetime.datetime.now(datetime.timezone.utc).date()
print(f"Run date: {run_date}")
silver_facilities = build_silver_facilities(silver_base, bronze, pincodes, run_date)

# COMMAND ----------

# Raises (and stops the run) if a row or Silver base value changed, the new columns
# aren't exactly the listed ones, or a flag is NULL.
check_silver_facilities(silver_base, silver_facilities)
print("Runtime checks passed")

# COMMAND ----------

print(format_flag_counts(flag_counts(silver_facilities)))

# COMMAND ----------

silver_facilities.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER["facilities"])
print(f"{SILVER_BASE['facilities']} -> {SILVER['facilities']}: {spark.table(SILVER['facilities']).count():,} rows")

# COMMAND ----------

display(spark.table(SILVER["facilities"]).limit(20))
