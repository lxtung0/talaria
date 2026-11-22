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
  - **Silver facilities**: `workspace.talaria.silver_facilities`, the final Silver stage, Silver base plus flag columns, built by `notebooks/03_silver_facilities`
- **Gold**: `workspace.talaria.gold_*`, aggregates and features for the analysis

Run notebooks in order:

1. `01_bronze_ingest`: source tables → bronze
2. `02_silver_base`: bronze facilities → Silver base. Runs the runtime checks (a failure stops the run before anything is written) and prints before/after counts per step.
3. `03_silver_facilities`: Silver base, bronze facilities and bronze pincodes → Silver facilities. Runs the runtime checks (a failure stops the run before anything is written) and prints true/false counts per flag.
4. Gold (to come)

## Code

- `talaria/silver_base/`: the Silver base cleaning module. Its one public entry point is `build_silver_base(bronze_df, pincodes_df) -> silver_base_df`, where `pincodes_df` is the bronze pincode directory each Facility's state is checked against ([ADR 0001](docs/adr/0001-silver-base-state-check.md)); it does no reads or writes, so it runs on any Spark session.
  - `columns.py`: which columns Silver base drops, parses, types and renames, and which Spelling fix or format rule each gets. The pipeline and the step counts both read these tables, so a new column or rule is one edit there.
  - `checks.py`: `check_silver_base(silver_base_df)`, the runtime checks the notebook runs on live data.
  - `step_counts.py`: `step_counts(bronze_df, silver_base_df)` and `format_step_counts`, the per-step counts the notebook prints, worked out by comparing bronze with the output.
- `talaria/silver_facilities/`: the Silver facilities module. Its one public entry point is `build_silver_facilities(silver_base_df, bronze_df, pincodes_df, run_date) -> silver_facilities_df`, with the same no-reads, no-writes rule.
  - `columns.py`: the new columns (name, group, type). The pipeline, runtime checks and flag counts all read this list.
  - `checks.py`: `check_silver_facilities(silver_base_df, silver_facilities_df)`, the runtime checks the notebook runs on live data.
  - `flag_counts.py`: `flag_counts` and `format_flag_counts`, the per-flag counts the notebook prints.
  - One module per flag group (`contacts.py` is group A, `size.py` B, `specialty.py` C, `description.py` D, `affiliation.py` E, `page_dates.py` G, `location.py` H). To add a group: write its `add_columns` in a new module, call it in `pipeline.py`, list its columns in `columns.py`.
- Notebooks import the package and `config.py` from the repo root (`sys.path.insert(0, os.path.abspath(".."))`), so run them from the Databricks Git folder.
- `tests/`: pytest tests that run against a local Spark session, no Databricks needed. `tests/conftest.py` has the `spark` fixture; `make_bronze`, which builds a small fake bronze facilities DataFrame from partial rows; `make_pincodes`, which builds a fake pincode directory from `(pincode, district, statename)` offices; `no_pincodes`, an empty directory for tests that don't exercise the state check; and `make_silver_inputs`, which builds matching bronze and Silver base inputs for the Silver facilities tests.

## Running tests locally

Needs [`uv`](https://docs.astral.sh/uv/) and a JDK 17 (Spark 3.5 runs on the JVM).

```sh
uv sync                                         # creates .venv with pyspark + pytest (dev group)
export JAVA_HOME=$(/usr/libexec/java_home -v 17) # macOS; elsewhere point JAVA_HOME at a JDK 17
uv run pytest
```

Test cleaning rules only through `build_silver_base`: build a fake bronze DataFrame with `make_bronze`, run `build_silver_base(bronze, no_pincodes)` (or a `make_pincodes(...)` directory for state-check rules), check the output rows and columns. The runtime checks and step counts have their own tests (`tests/test_checks.py`, `tests/test_step_counts.py`).

Test Silver facilities rules only through `build_silver_facilities`: get `bronze, silver_base` from `make_silver_inputs(...)`, build with a fixed run date, check the output. Its runtime checks and flag counts are tested in `tests/test_silver_facilities_checks.py`.

## Working in Databricks

1. Link GitHub: profile icon → Settings → Linked accounts → GitHub.
2. Workspace → Create → Git folder → `https://github.com/lxtung0/talaria`.
3. Create a branch per person, commit & push often, and pull before you start editing.
4. Don't commit data files. Data stays in Unity Catalog.
