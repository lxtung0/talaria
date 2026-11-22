# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Care finder demo
# MAGIC Runs `recommend()` (ticket #28) for the five demo queries and prints each answer: the resolved location,
# MAGIC the search extent, and the top Facilities with their verbatim quotes, labels, warnings and good points.
# MAGIC Reads the app tables built by `03_app_tables` and the Vector Search index; writes only the label cache
# MAGIC `workspace.talaria.app_item_labels`.

# COMMAND ----------

# MAGIC %pip install -q "h3>=4,<5"

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.path.abspath(".."))
from talaria.care_finder.recommend import recommend

DEMO_QUERIES = [
    ("dialysis", "Patna", "planned"),
    ("emergency C-section", "Lucknow", "emergency"),
    ("kidney machine", "800001", "planned"),
    ("MRI", "Jaipur", "planned"),
    ("NICU", "25.59,85.14", "emergency"),
]


def show(answer: dict) -> None:
    print(f"=== {answer['service']} / {answer['location_query']} ({answer['urgency']}) → {answer['status']}")
    if answer["status"] == "error":
        print("  ", answer["error"])
        return
    if answer["status"] == "ambiguous":
        print("   Which one?", "; ".join(answer["candidates"]))
        return
    s = answer["search"]
    print(f"   at {answer['location']['label']}; searched k={s['searched_k']} (~{s['searched_radius_km']} km) "
          f"in {s['rounds']} rounds, stop: {s['stop_reason']}; evidence checked: {answer['evidence_checked']}")
    if not answer["top"]:
        print(f"   No facility with evidence within {s['searched_radius_km']} km")
    for i, r in enumerate(answer["top"] + answer["others"], 1):
        group = "top" if i <= len(answer["top"]) else "other"
        print(f"   [{group}] {r['name']} ({r['facility_type']}), {r['distance_km']} km, "
              f"evidence {r['evidence_band']} ({r['service_evidence']}), confidence {r['confidence_band']}, rank {r['rank']}")
        for e in r["evidence"][:3]:
            print(f"      {e['label']:<8} {e['item_type']:<21} \"{e['item_text']}\" ({e['similarity']}) — {e['reason']}")
        for line in r["good_points"]:
            print(f"      ✓ {line}")
        for line in r["warnings"]:
            print(f"      ⚠ {line}")


# COMMAND ----------

import contextlib
import io

# Printed here and also returned as the run's exit value, so a `jobs submit` run can be read back.
log = io.StringIO()
for service, location, urgency in DEMO_QUERIES:
    with contextlib.redirect_stdout(log):
        show(recommend(service, location, urgency))
        print()
print(log.getvalue())

# COMMAND ----------

dbutils.notebook.exit(log.getvalue()[-60000:])
