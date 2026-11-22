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
# Silver Stage 3: Silver facilities plus capacity, large-hospital and consistency flags (#35),
# and its per-rule counts.
SILVER_STAGE3 = {
    "facilities": _out("silver", "facilities_stage3"),
    "rule_counts": _out("silver", "stage3_rule_counts"),
}
GOLD = {}  # add gold tables here as the analysis takes shape, e.g. GOLD["facilities_by_district"] = _out("gold", "facilities_by_district")
