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
- **Gold**: `workspace.talaria.gold_*`, built by `notebooks/04_gold` (spec #37)
  - `workspace.talaria.gold_facilities`: one row per Facility, with `confidence_score` (0–1), its log `confidence_reasons` and `location_uncertain`
  - `workspace.talaria.gold_facility_items`: one row per claim (specialty, procedure, equipment, capability, description sentence), verbatim

Run notebooks in order:

1. `01_bronze_ingest`: source tables → bronze
2. `02_silver_base`: bronze facilities → Silver base. Runs the runtime checks (a failure stops the run before anything is written) and prints before/after counts per step.
3. `03_silver_facilities`: Silver base, bronze facilities and bronze pincodes → Silver facilities. Runs the runtime checks (a failure stops the run before anything is written) and prints true/false counts per flag.
4. `04_gold`: Silver facilities → both Gold tables. Runs the runtime checks (a failure stops the run before anything is written) and prints per-rule fire counts and the score distribution.

## Code

- `talaria/silver_base/`: the Silver base cleaning module. Its one public entry point is `build_silver_base(bronze_df, pincodes_df) -> silver_base_df`, where `pincodes_df` is the bronze pincode directory each Facility's state is checked against ([ADR 0001](docs/adr/0001-silver-base-state-check.md)); it does no reads or writes, so it runs on any Spark session.
  - `columns.py`: which columns Silver base drops, parses, types and renames, and which Spelling fix or format rule each gets. The pipeline and the step counts both read these tables, so a new column or rule is one edit there.
  - `checks.py`: `check_silver_base(silver_base_df)`, the runtime checks the notebook runs on live data.
  - `step_counts.py`: `step_counts(bronze_df, silver_base_df)` and `format_step_counts`, the per-step counts the notebook prints, worked out by comparing bronze with the output.
- `talaria/silver_facilities/`: the Silver facilities module. Its one public entry point is `build_silver_facilities(silver_base_df, bronze_df, pincodes_df, run_date) -> silver_facilities_df`, with the same no-reads, no-writes rule.
  - `columns.py`: the new columns (name, group, type). The pipeline, runtime checks and flag counts all read this list.
  - `checks.py`: `check_silver_facilities(silver_base_df, silver_facilities_df)`, the runtime checks the notebook runs on live data.
  - `flag_counts.py`: `flag_counts` and `format_flag_counts`, the per-flag counts the notebook prints.
  - One module per flag group (`contacts.py` is group A, `size.py` B, `specialty.py` C, `description.py` D, `affiliation.py` E, `sources.py` F, `page_dates.py` G, `location.py` H). To add a group: write its `add_columns` in a new module, call it in `pipeline.py`, list its columns in `columns.py`.
- `talaria/gold/`: the Gold module. Its one public entry point is `build_gold(silver_facilities_df) -> (gold_facilities_df, gold_facility_items_df)`, with the same no-reads, no-writes rule.
  - `scoring.py`: the tiers (points and caps) and the rule table, one rule per scored flag ([ADR 0003](docs/adr/0003-gold-confidence-score.md)). To change a weight, edit `TIERS`; to move or add a flag, edit `RULES`.
  - `columns.py`: both table schemas, the contract with the app.
  - `items.py`: Table B, including the sentence split and its abbreviation list.
  - `checks.py`: `check_gold(silver_facilities_df, gold_facilities_df, gold_facility_items_df)`, including a replay of every score from its log.
  - `score_counts.py`: per-rule fire counts, worst tier per Facility and the score distribution the notebook prints.
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

Test Gold only through `build_gold`, on real Silver facilities output with the flags you need set by hand (`tests/test_gold.py`).

## Working in Databricks

1. Link GitHub: profile icon → Settings → Linked accounts → GitHub.
2. Workspace → Create → Git folder → `https://github.com/lxtung0/talaria`.
3. Create a branch per person, commit & push often, and pull before you start editing.
4. Don't commit data files. Data stays in Unity Catalog.
