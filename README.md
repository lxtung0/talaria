# talaria

Datathon project using the **Virtue Foundation dataset** on Databricks.

## Data

Source tables (Unity Catalog, read-only):

| Key | Table | Rows |
|---|---|---|
| `facilities` | `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities` | ~10k |
| `pincodes` | `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.india_post_pincode_directory` | ~166k |
| `nfhs5` | `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.nfhs_5_district_health_indicators` | ~700 |

All table names live in [`config.py`](config.py). Notebooks import from it instead of hard-coding names.

## Layout (medallion)

- **Bronze**: `workspace.talaria.bronze_*`, raw snapshots of the source tables, built by `notebooks/01_bronze_ingest`
- **Silver**: `workspace.talaria.silver_*`, cleaned, typed, de-duplicated
  - **Silver base**: `workspace.talaria.silver_facilities_base`, objective fixes only, built by `notebooks/02_silver_base`
  - **Silver facilities**: `workspace.talaria.silver_facilities`, the final Silver stage, read from Silver base (not built yet)
- **Gold**: `workspace.talaria.gold_*`, aggregates and features for the analysis

Run notebooks in order:

1. `01_bronze_ingest`: source tables → bronze
2. `02_silver_base`: bronze facilities → Silver base. Runs the runtime checks (a failure stops the run before anything is written) and prints before/after counts per step.
3. Silver facilities, then gold (to come)

## Code

- `talaria/silver_base/`: the Silver base cleaning module. Its one public entry point is `build_silver_base(bronze_df) -> silver_base_df`; it does no reads or writes, so it runs on any Spark session.
  - `checks.py`: `check_silver_base(silver_base_df)`, the runtime checks the notebook runs on live data.
  - `step_counts.py`: `step_counts(bronze_df, silver_base_df)` and `format_step_counts`, the per-step counts the notebook prints, worked out by comparing bronze with the output.
- Notebooks import the package and `config.py` from the repo root (`sys.path.insert(0, os.path.abspath(".."))`), so run them from the Databricks Git folder.
- `tests/`: pytest tests that run against a local Spark session, no Databricks needed. `tests/conftest.py` has the `spark` fixture and `make_bronze`, which builds a small fake bronze facilities DataFrame from partial rows.

## Running tests locally

Needs [`uv`](https://docs.astral.sh/uv/) and a JDK 17 (Spark 3.5 runs on the JVM).

```sh
uv sync                                         # creates .venv with pyspark + pytest (dev group)
export JAVA_HOME=$(/usr/libexec/java_home -v 17) # macOS; elsewhere point JAVA_HOME at a JDK 17
uv run pytest
```

Test cleaning rules only through `build_silver_base`: build a fake bronze DataFrame with `make_bronze`, run the function, check the output rows and columns. The runtime checks and step counts have their own tests (`tests/test_checks.py`, `tests/test_step_counts.py`).

## Working in Databricks

1. Link GitHub: profile icon → Settings → Linked accounts → GitHub.
2. Workspace → Create → Git folder → `https://github.com/lxtung0/talaria`.
3. Create a branch per person, commit & push often, and pull before you start editing.
4. Don't commit data files. Data stays in Unity Catalog.
