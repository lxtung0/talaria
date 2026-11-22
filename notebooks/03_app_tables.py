# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · App tables (care finder)
# MAGIC Builds the two care finder tables from the source Facilities table set in `config.py` (ticket #27):
# MAGIC `app_facilities` (one row per Facility, with `h3_r5`) and `app_facility_items` (one row per claim).
# MAGIC Then creates the Vector Search endpoint if it's missing and creates or syncs the Delta Sync index on the items.
# MAGIC Writes only `workspace.talaria.app_*` tables.

# COMMAND ----------

import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(".."))
from config import APP, APP_EMBEDDING_MODEL, APP_SEARCH_PATH, APP_SOURCE_FACILITIES, APP_VS_ENDPOINT, APP_VS_INDEX

from delta.tables import DeltaTable
from pyspark.sql import functions as F

from talaria.care_finder.items import build_app_tables

# COMMAND ----------

source = spark.table(APP_SOURCE_FACILITIES)
facilities, items = build_app_tables(source)

# H3 functions only exist on Databricks, so `h3_r5` is added here, not in the package.
h3_r5 = F.when(
    F.col("latitude").isNotNull() & F.col("longitude").isNotNull(),
    F.expr("h3_longlatash3string(longitude, latitude, 5)"),
)
facilities = facilities.withColumn("h3_r5", h3_r5)
facilities.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(APP["facilities"])
print(f"{APP_SOURCE_FACILITIES} -> {APP['facilities']}: {spark.table(APP['facilities']).count():,} rows")

# COMMAND ----------

items = items.join(spark.table(APP["facilities"]).select("unique_id", "h3_r5"), "unique_id").select(
    "item_id", "unique_id", "item_type", "item_text", "h3_r5"
)

# Merge rather than overwrite, so a rebuild only changes rows whose text or cell
# changed, and the triggered index sync only re-embeds those.
if spark.catalog.tableExists(APP["facility_items"]):
    updated = {c: f"s.{c}" for c in ["unique_id", "item_type", "item_text", "h3_r5"]}
    if "embedding" in spark.table(APP["facility_items"]).columns:
        # A changed text needs a new embedding (the Delta fallback fills NULLs below).
        updated["embedding"] = "CASE WHEN t.item_text <=> s.item_text THEN t.embedding END"
    (
        DeltaTable.forName(spark, APP["facility_items"]).alias("t")
        .merge(items.alias("s"), "t.item_id = s.item_id")
        .whenMatchedUpdate(
            condition="NOT (t.item_text <=> s.item_text AND t.h3_r5 <=> s.h3_r5 AND t.item_type <=> s.item_type)",
            set=updated,
        )
        .whenNotMatchedInsert(values={c: f"s.{c}" for c in items.columns})
        .whenNotMatchedBySourceDelete()
        .execute()
    )
else:
    items.write.option("delta.enableChangeDataFeed", "true").saveAsTable(APP["facility_items"])
# Delta Sync needs Change Data Feed.
spark.sql(f"ALTER TABLE {APP['facility_items']} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")

# COMMAND ----------

counts = spark.table(APP["facility_items"]).groupBy("item_type").count().orderBy("item_type").collect()
summary = [f"{row.item_type:<22}{row['count']:>10,}" for row in counts]
summary.append(f"{'total':<22}{sum(r['count'] for r in counts):>10,}")
print("\n".join(summary))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Fallback: Delta embeddings
# MAGIC Only when `APP_SEARCH_PATH = "delta"` in `config.py` (Free Edition refused the endpoint or index).
# MAGIC Fills an `embedding` column once with `ai_query`, embedding each distinct text one time,
# MAGIC and only for rows that don't have one yet. The Vector Search cells below are then skipped.

# COMMAND ----------

if APP_SEARCH_PATH == "delta":
    if "embedding" not in spark.table(APP["facility_items"]).columns:
        spark.sql(f"ALTER TABLE {APP['facility_items']} ADD COLUMNS (embedding ARRAY<FLOAT>)")
    spark.sql(f"""
        MERGE INTO {APP['facility_items']} t
        USING (SELECT item_text, ai_query('{APP_EMBEDDING_MODEL}', item_text) AS embedding
               FROM (SELECT DISTINCT item_text FROM {APP['facility_items']} WHERE embedding IS NULL)) s
        ON t.item_text = s.item_text AND t.embedding IS NULL
        WHEN MATCHED THEN UPDATE SET t.embedding = s.embedding""")
    filled = spark.table(APP["facility_items"]).where("embedding IS NOT NULL").count()
    summary.append(f"Delta fallback: {filled:,} items have embeddings")
    # Test query: "kidney machine" in one Patna-area H3 cell, by cosine similarity.
    test = spark.sql(f"""
        WITH q AS (SELECT ai_query('{APP_EMBEDDING_MODEL}', 'kidney machine') AS v)
        SELECT item_type, item_text,
            aggregate(zip_with(embedding, q.v, (a, b) -> a * b), 0D, (acc, x) -> acc + x)
            / (sqrt(aggregate(embedding, 0D, (acc, x) -> acc + x * x)) * sqrt(aggregate(q.v, 0D, (acc, x) -> acc + x * x))) AS similarity
        FROM {APP['facility_items']} CROSS JOIN q
        WHERE h3_r5 = h3_longlatash3string(85.1376, 25.5941, 5)
        ORDER BY similarity DESC LIMIT 10""").collect()
    summary.append('"kidney machine" in the Patna cell:')
    summary.extend(f"  {r.similarity:.3f} {r.item_type:<12} {r.item_text}" for r in test)
    print("\n".join(summary))
    dbutils.notebook.exit("\n".join(summary))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Vector Search endpoint and index

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingSourceColumn,
    EndpointType,
    PipelineType,
    VectorIndexType,
)

w = WorkspaceClient()

if APP_VS_ENDPOINT not in [e.name for e in w.vector_search_endpoints.list_endpoints()]:
    print(f"Creating endpoint {APP_VS_ENDPOINT}")
    w.vector_search_endpoints.create_endpoint_and_wait(name=APP_VS_ENDPOINT, endpoint_type=EndpointType.STANDARD)
print(f"Endpoint {APP_VS_ENDPOINT}: {w.vector_search_endpoints.get_endpoint(APP_VS_ENDPOINT).endpoint_status.state}")

# COMMAND ----------

existing = [i.name for i in w.vector_search_indexes.list_indexes(endpoint_name=APP_VS_ENDPOINT)]
if APP_VS_INDEX in existing:
    print(f"Syncing {APP_VS_INDEX}")
    w.vector_search_indexes.sync_index(index_name=APP_VS_INDEX)
else:
    print(f"Creating {APP_VS_INDEX}")
    w.vector_search_indexes.create_index(
        name=APP_VS_INDEX,
        endpoint_name=APP_VS_ENDPOINT,
        primary_key="item_id",
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=APP["facility_items"],
            pipeline_type=PipelineType.TRIGGERED,
            embedding_source_columns=[
                EmbeddingSourceColumn(name="item_text", embedding_model_endpoint_name=APP_EMBEDDING_MODEL)
            ],
            columns_to_sync=["item_id", "unique_id", "item_type", "item_text", "h3_r5"],
        ),
    )

# COMMAND ----------

# The first sync embeds every item and can take a long time, so this only waits a
# few minutes; re-run this cell (or check the index page) until it is ONLINE.
for _ in range(10):
    status = w.vector_search_indexes.get_index(APP_VS_INDEX).status
    print(f"ready={status.ready} indexed_rows={status.indexed_row_count} {status.message}")
summary.append(f"index ready={status.ready} indexed_rows={status.indexed_row_count} {status.message}")
    if status.ready:
        break
    time.sleep(30)

# COMMAND ----------

# Test query: "kidney machine" in one Patna-area H3 cell.
patna_cell = spark.sql("SELECT h3_longlatash3string(85.1376, 25.5941, 5) AS c").first().c
if w.vector_search_indexes.get_index(APP_VS_INDEX).status.ready:
    result = w.vector_search_indexes.query_index(
        index_name=APP_VS_INDEX,
        columns=["item_id", "item_type", "item_text"],
        query_text="kidney machine",
        filters_json=json.dumps({"h3_r5": [patna_cell]}),
        num_results=10,
    )
    summary.append(f'"kidney machine" in Patna cell {patna_cell}:')
    summary.extend(str(row) for row in result.result.data_array or [])
else:
    summary.append(f"Index not ready yet; test query skipped (cell {patna_cell})")
print("\n".join(summary))

# COMMAND ----------

dbutils.notebook.exit("\n".join(summary))
