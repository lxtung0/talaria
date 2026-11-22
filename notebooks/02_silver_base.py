# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Silver base
# MAGIC Builds the first Silver stage for facilities: objective fixes only (spec #1).
# MAGIC Reads bronze facilities and the bronze pincode directory, runs `build_silver_base`, checks the result against live data,
# MAGIC prints before/after counts per step, then overwrites the Silver base table.
# MAGIC A failed runtime check stops the run before anything is written.

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.path.abspath(".."))
from config import BRONZE, SILVER_BASE

from talaria.silver_base import build_silver_base
from talaria.silver_base.checks import check_silver_base
from talaria.silver_base.step_counts import format_step_counts, step_counts

# COMMAND ----------

bronze = spark.table(BRONZE["facilities"])
# Each Facility's state is checked against the pincode directory (#9).
pincodes = spark.table(BRONZE["pincodes"])
silver_base = build_silver_base(bronze, pincodes)

# COMMAND ----------

# Raises (and stops the run) if unique_id is null or repeated, a text column holds a
# Missing-value spelling, or a list column holds an empty item or an empty list.
check_silver_base(silver_base)
print("Runtime checks passed")

# COMMAND ----------

print(format_step_counts(step_counts(bronze, silver_base)))

# COMMAND ----------

silver_base.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER_BASE["facilities"])
print(f"{BRONZE['facilities']} -> {SILVER_BASE['facilities']}: {spark.table(SILVER_BASE['facilities']).count():,} rows")

# COMMAND ----------

display(spark.table(SILVER_BASE["facilities"]).limit(20))
