---
status: proposed
---

# Silver Stage 3 mappings live as CSVs in the repo

Silver Stage 3 (#35) maps each specialty code to a category, finds categories in free text with regexes, and checks procedures against equipment. It needs six hand-built tables for this: `specialty_category_map_v3` (about 2,780 codes), `ref_text_category_keywords`, `ref_related_categories`, `ref_procedure_equipment_rules`, `ref_capability_units` and `ref_high_risk_categories`. They were first uploaded to Databricks as tables.

ADR 0002 says a reference table lives in the repo as Python data, and that each row cites an official document. These six tables don't fit that:

- They are the project's own mappings, like the specialty synonyms of #17, not outside knowledge copied from a standard, so there is no document to cite.
- A 2,780-row code map is easier to review and edit as a CSV than as Python data.

So these tables live as CSVs in `talaria/silver_stage3/reference/`, next to the code that reads them. `load_references()` reads them, and they are the only source for Stage 3's mappings and patterns. The notebook reads the repo copy, not uploaded tables, so the Databricks run and the local tests use the same patterns.

## Consequences

- A change to a pattern or a mapping is a commit, reviewed like code. Stage 3's expected counts in #35 depend on these files, so a change should restate the counts it moves.
- They are not Reference tables in the glossary's sense (cited outside knowledge). They are only compared against facility data, and never fill or change a Facility value.
- The uploaded Databricks copies are no longer read and can be dropped.
