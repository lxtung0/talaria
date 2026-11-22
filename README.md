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
  - **Silver facilities**: `workspace.talaria.silver_facilities`, Silver base plus flag columns, built by `notebooks/03_silver_facilities`
  - **Silver Stage 3**: `workspace.talaria.silver_facilities_stage3`, Silver facilities plus capacity, large-hospital and consistency flags, with its rule log in `workspace.talaria.silver_stage3_rule_counts`, built by `notebooks/05_silver_stage3`
- **Gold**: `workspace.talaria.gold_*`, aggregates and features for the analysis

Run notebooks in order:

1. `01_bronze_ingest`: source tables → bronze
2. `02_silver_base`: bronze facilities → Silver base. Runs the runtime checks (a failure stops the run before anything is written) and prints before/after counts per step.
3. `03_silver_facilities`: Silver base, bronze facilities and bronze pincodes → Silver facilities. Runs the runtime checks (a failure stops the run before anything is written) and prints true/false counts per flag.
4. `05_silver_stage3`: Silver facilities → Silver Stage 3. Prints the cross-tabs of the two Stage 2 flags it replaces, runs the runtime checks (a failure stops the run before anything is written), writes the table and its rule log, and shows sample rows for C2-C5.
5. Gold (to come)

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
- `talaria/silver_stage3/`: the Silver Stage 3 module (#35). Its public entry point is `build_silver_stage3(silver_facilities_df, references=None) -> stage3_df`, with the same no-reads, no-writes rule; `load_references()` reads the reference CSVs, and is the default.
  - `reference/`: the six reference CSVs (specialty code → category, text keywords per category, related categories, procedure/equipment rules, capability units, high-risk categories), the only source of Stage 3's mappings and patterns ([ADR 0003](docs/adr/0003-stage3-reference-csvs.md)). Edit a pattern there, not in code.
  - `columns.py`: the two Stage 2 flags Stage 3 replaces and drops, and the new columns (name, step, type). The last, `evidence_items`, cites the facility text behind every true C2-C5 flag (`{rule, field, item, subject}`, item verbatim), so Gold can quote it.
  - `checks.py`: `check_silver_stage3(silver_facilities_df, stage3_df)`, the runtime checks the notebook runs on live data.
  - `rule_counts.py`: `rule_counts`, the rule log, and `replaced_flag_crosstabs`.
  - One module per step: `specialty_categories.py` (step 1), `capacity.py` (R0), `name_type.py` (F1), `large_hospital.py` (R1-R5), `consistency.py` (C1-C5); `text.py` holds the shared definitions.
- `talaria/care_finder/`: the care finder app's logic (spec #26). `items.py` is the only Spark module: `build_app_tables(facilities) -> (app_facilities, app_facility_items)` for `03_app_tables`. The rest is plain Python, so the app imports it without Spark:
  - `recommend.py`: `recommend(service, location, urgency)`, the query flow. All IO goes through `backend.py` (SQL warehouse, search, model serving), so tests pass a fake backend.
  - `search.py`: the expanding H3 ring loop; `labels.py`: the LLM check prompt, output validation and similarity fallback; `scoring.py`: hit values, noisy-OR, rank and bands; `reasons.py`: flag → fixed warning or ✓ line; `location.py`: PIN / district / city / coordinates parsing.
  - `settings.py`: every tunable number. `present.py`: the UI's text templates. `search_map.py`: the animated pydeck map.
- `app/`: the Streamlit app (`app.py`, `app.yaml`, `requirements.txt`). `scripts/build_app.sh` bundles it with the package for deploy.
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

Test Silver Stage 3 rules only through `build_silver_stage3`, on Silver facilities built from `make_silver_inputs(...)` and the reference CSVs in the repo (`tests/test_silver_stage3.py`).

## Running the app

The care finder (spec #26) is a Streamlit Databricks App, `talaria-care-finder`: a service and a location in, the best 3 Facilities out, each with verbatim quotes, warnings and a "How we decided" section.

**Build its data** (once, and after the source table changes): run `notebooks/03_app_tables`. It writes `app_facilities` and `app_facility_items` (one row per claim). With `APP_SEARCH_PATH = "delta"` in `config.py`, the current setting, it fills an `embedding` column with `ai_query`, and the app finds matching claims by cosine similarity in SQL. With `"vector_search"` it creates or syncs the Vector Search index `app_facility_items_index` on endpoint `talaria-vs` instead, which was too slow to fill on Free Edition. `notebooks/04_recommend_demo` runs five demo queries through `recommend()`.

**Local run** (uses your `DEFAULT` Databricks CLI profile):

```sh
uv sync
uv run streamlit run app/app.py
```

**Deploy:** `./scripts/deploy_app.sh` applies the app's permissions, stages `app/` plus `config.py` and `talaria/care_finder/` into `build/app`, uploads it to the workspace and deploys. It starts the app if it's stopped.

**Stop / start** (the app uses Free Edition compute while running):

```sh
databricks apps stop talaria-care-finder
databricks apps start talaria-care-finder   # then open the URL from: databricks apps get talaria-care-finder
```

**Gold:** `03_app_tables` takes each Facility's `confidence_score` and `confidence_reasons` from `gold_facilities` (`APP_CONFIDENCE_SOURCE` in `config.py`) and keeps only the Facilities Gold covers. The claim lists and flags still come from Silver facilities, because Gold doesn't carry them. Without a Gold table it falls back to 0.5. After re-running `06_gold`, re-run `03_app_tables` and redeploy.

**Tuning:** every scoring number and search setting is in `talaria/care_finder/settings.py`.

## Working in Databricks

1. Link GitHub: profile icon → Settings → Linked accounts → GitHub.
2. Workspace → Create → Git folder → `https://github.com/lxtung0/talaria`.
3. Create a branch per person, commit & push often, and pull before you start editing.
4. Don't commit data files. Data stays in Unity Catalog.
