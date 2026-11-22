# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Silver NFHS-5
# MAGIC Cleans the NFHS-5 district health indicators (#41): one typed row per district.
# MAGIC Values are trimmed and typed, states get the project's official names, and the NFHS-5 markers are kept as lists:
# MAGIC `*` (suppressed, under 25 cases) is NULL and listed in `suppressed_columns`; `(x)` (25-49 cases) is `x` and listed in `low_sample_columns`.
# MAGIC Linking districts to facilities is not done here. A failed runtime check stops the run before anything is written.

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.path.abspath(".."))
from config import BRONZE, SILVER

from talaria.silver_nfhs5 import build_silver_nfhs5
from talaria.silver_nfhs5.checks import check_silver_nfhs5
from talaria.silver_nfhs5.marker_counts import format_marker_counts, marker_counts

# COMMAND ----------

bronze = spark.table(BRONZE["nfhs5"])
silver_nfhs5 = build_silver_nfhs5(bronze)

# COMMAND ----------

# Raises (and stops the run) on a lost row, a repeated or unrecognised district, a missing
# survey size, or an indicator value that isn't a number, `*` or `(number)`.
check_silver_nfhs5(bronze, silver_nfhs5)
print("Runtime checks passed")

# COMMAND ----------

print(format_marker_counts(marker_counts(silver_nfhs5)))

# COMMAND ----------

silver_nfhs5.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER["nfhs5"])
print(f"{BRONZE['nfhs5']} -> {SILVER['nfhs5']}: {spark.table(SILVER['nfhs5']).count():,} rows")

# COMMAND ----------

display(spark.table(SILVER["nfhs5"]).limit(20))
