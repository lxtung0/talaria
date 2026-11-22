# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Silver Stage 3
# MAGIC Builds Silver Stage 3 (#35): Silver facilities plus capacity outlier (R0), name vs type (F1), large hospital (R1-R5)
# MAGIC and consistency (C1-C5) flags. Two Stage 2 flags it replaces are dropped. Values are never changed and nothing is scored.
# MAGIC The mappings and patterns come from the reference CSVs in `talaria/silver_stage3/reference/`.
# MAGIC A failed runtime check stops the run before anything is written.

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.path.abspath(".."))
from config import SILVER, SILVER_STAGE3

from talaria.silver_stage3 import build_silver_stage3, load_references
from talaria.silver_stage3.checks import check_silver_stage3
from talaria.silver_stage3.rule_counts import replaced_flag_crosstabs, rule_counts

# COMMAND ----------

silver_facilities = spark.table(SILVER["facilities"])
stage3 = build_silver_stage3(silver_facilities, load_references()).cache()

# COMMAND ----------

# MAGIC %md
# MAGIC Each dropped Stage 2 flag against the Stage 3 flag replacing it, for the record.
# MAGIC Expected overlap: 29 of 29 for the ratio outlier; about 343 for the specialty flag.

# COMMAND ----------

for old, crosstab in replaced_flag_crosstabs(silver_facilities, stage3).items():
    print(old)
    crosstab.show()

# COMMAND ----------

# Raises (and stops the run) if a row or kept value changed, the columns aren't exactly
# the expected ones, or a flag is NULL.
check_silver_stage3(silver_facilities, stage3)
print("Runtime checks passed")

# COMMAND ----------

stage3.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER_STAGE3["facilities"])
log = rule_counts(spark.table(SILVER_STAGE3["facilities"]))
log.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER_STAGE3["rule_counts"])
print(f"{SILVER['facilities']} -> {SILVER_STAGE3['facilities']}: {spark.table(SILVER_STAGE3['facilities']).count():,} rows")
display(spark.table(SILVER_STAGE3["rule_counts"]))

# COMMAND ----------

# MAGIC %md
# MAGIC Five sample rows per consistency rule.

# COMMAND ----------

written = spark.table(SILVER_STAGE3["facilities"])
for flag, reason in [
    ("flag_partial", "partial_reason"),
    ("flag_specialty_unsupported", "unsupported_specialties"),
    ("flag_major_orphan", "orphan_reason"),
    ("flag_merge_different", "core_categories"),
]:
    print(flag)
    display(written.where(flag).select("name", "specialty_categories", reason).limit(5))
