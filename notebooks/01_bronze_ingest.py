# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze ingest
# MAGIC Snapshots the Virtue Foundation source tables into our own bronze tables, untouched apart from load metadata.
# MAGIC Silver cleaning notebooks read from these bronze tables, never from the source directly.

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.path.abspath(".."))
from config import BRONZE, OUTPUT_CATALOG, OUTPUT_SCHEMA, SOURCE

from pyspark.sql import functions as F

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {OUTPUT_CATALOG}.{OUTPUT_SCHEMA}")

# COMMAND ----------

for name, source_table in SOURCE.items():
    df = (
        spark.table(source_table)
        .withColumn("_source_table", F.lit(source_table))
        .withColumn("_ingested_at", F.current_timestamp())
    )
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(BRONZE[name])
    print(f"{source_table} -> {BRONZE[name]}: {spark.table(BRONZE[name]).count():,} rows")

# COMMAND ----------

display(spark.table(BRONZE["facilities"]).limit(20))
