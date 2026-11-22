"""Shared table names for the talaria project.

Import this from any notebook so table names live in one place:

    import sys, os
    sys.path.insert(0, os.path.abspath(".."))  # from notebooks/
    from config import SOURCE, BRONZE, SILVER_BASE, SILVER, SILVER_STAGE3, GOLD, OUTPUT_CATALOG, OUTPUT_SCHEMA
"""

# Source: the Virtue Foundation datathon dataset (read-only, Unity Catalog)
SOURCE_CATALOG = "databricks_virtue_foundation_dataset_dais_2026"
SOURCE_SCHEMA = "virtue_foundation_dataset"

SOURCE = {
    "facilities": f"{SOURCE_CATALOG}.{SOURCE_SCHEMA}.facilities",
    "pincodes": f"{SOURCE_CATALOG}.{SOURCE_SCHEMA}.india_post_pincode_directory",
    "nfhs5": f"{SOURCE_CATALOG}.{SOURCE_SCHEMA}.nfhs_5_district_health_indicators",
}

# Output: where our bronze/silver/gold tables are written.
# Change OUTPUT_CATALOG if you can't write to `workspace` in your workspace.
OUTPUT_CATALOG = "workspace"
OUTPUT_SCHEMA = "talaria"


def _out(layer: str, name: str) -> str:
    return f"{OUTPUT_CATALOG}.{OUTPUT_SCHEMA}.{layer}_{name}"


BRONZE = {name: _out("bronze", name) for name in SOURCE}
SILVER = {name: _out("silver", name) for name in SOURCE}
# Silver base: the first Silver stage (objective fixes only). SILVER["facilities"]
# is Silver facilities, the final Silver stage, which reads from this.
SILVER_BASE = {"facilities": _out("silver", "facilities_base")}
# Each facility's NFHS-5 district (#44): joins SILVER["nfhs5"] to facilities.
SILVER_FACILITY_DISTRICTS = _out("silver", "facility_districts")
# Silver Stage 3: Silver facilities plus capacity, large-hospital and consistency flags (#35),
# and its per-rule counts.
SILVER_STAGE3 = {
    "facilities": _out("silver", "facilities_stage3"),
    "rule_counts": _out("silver", "stage3_rule_counts"),
}
# Gold (spec #37): one row per Facility with its confidence score, and one row per claim.
# Built from Silver Stage 3. Plus the district cells the care finder looks up.
GOLD = {
    "facilities": _out("gold", "facilities"),
    "facility_items": _out("gold", "facility_items"),
    # One row per H3 res-5 cell with post offices: its NFHS-5 district and the indicators the app shows.
    "district_cells": _out("gold", "district_cells"),
}

# Care finder app (spec #26). The app reads one source Facilities table; swap
# APP_SOURCE_FACILITIES to the Gold table once it exists (a one-line change).
APP_SOURCE_FACILITIES = SILVER["facilities"]
APP = {
    "facilities": _out("app", "facilities"),
    "facility_items": _out("app", "facility_items"),
    "item_labels": _out("app", "item_labels"),
}
APP_PINCODES = BRONZE["pincodes"]
APP_VS_ENDPOINT = "talaria-vs"
APP_VS_INDEX = f"{OUTPUT_CATALOG}.{OUTPUT_SCHEMA}.app_facility_items_index"
APP_EMBEDDING_MODEL = "databricks-gte-large-en"
# "vector_search" (the index) or "delta" (the fallback: an `embedding` column on
# app_facility_items, searched in SQL), if Free Edition refuses the endpoint or index.
APP_SEARCH_PATH = "delta"
APP_CHAT_MODEL = "databricks-meta-llama-3-3-70b-instruct"
APP_WAREHOUSE_ID = "3a60f8ef7e0a6731"  # Serverless Starter Warehouse
APP_NAME = "talaria-care-finder"
