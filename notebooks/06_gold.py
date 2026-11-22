# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Gold
# MAGIC Builds the Gold tables (spec #37) from Silver Stage 3 (run `05_silver_stage3` first):
# MAGIC - `gold_facilities`: one row per Facility, with `confidence_score` (0–1) and its log, `confidence_reasons`
# MAGIC - `gold_facility_items`: one row per claim (specialty, procedure, equipment, capability, description sentence)
# MAGIC
# MAGIC Runs `build_gold`, checks both tables, prints per-rule fire counts and the score distribution, then overwrites both tables.
# MAGIC A failed runtime check stops the run before anything is written. Weights and tiers live in `talaria/gold/scoring.py`.

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.path.abspath(".."))
from config import GOLD, SILVER_STAGE3

from talaria.gold import build_gold
from talaria.gold.checks import check_gold
from talaria.gold.score_counts import format_score_counts, score_counts

# COMMAND ----------

silver_stage3 = spark.table(SILVER_STAGE3["facilities"])
gold_facilities, gold_facility_items = build_gold(silver_stage3)

# COMMAND ----------

# Raises (and stops the run) if a row or copied value changed, a score doesn't
# replay from its log, or an item count differs from its Silver list.
check_gold(silver_stage3, gold_facilities, gold_facility_items)
print("Runtime checks passed")

# COMMAND ----------

print(format_score_counts(score_counts(silver_stage3, gold_facilities)))

# COMMAND ----------

gold_facilities.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(GOLD["facilities"])
gold_facility_items.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(GOLD["facility_items"])
for name in GOLD.values():
    print(f"{name}: {spark.table(name).count():,} rows")

# COMMAND ----------

display(spark.table(GOLD["facilities"]).orderBy("confidence_score").limit(20))

# COMMAND ----------

display(spark.table(GOLD["facility_items"]).limit(20))
