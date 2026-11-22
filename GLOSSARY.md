# Talaria

Datathon project assessing Indian healthcare facilities from the Virtue Foundation dataset, cleaned in medallion layers before any judgement of data quality.

## Language

### Data layers

**Silver**:
The layer where only objective mistakes are fixed: wrong types, broken rows, duplicate rows, placeholder nulls, impossible values, and a state that its PIN and city agree is wrong. Silver never judges how trustworthy a source or value is.
_Avoid_: clean data (ambiguous), validated data

**Silver base**:
The first Silver stage, made of easy, objective fixes: broken and duplicate rows removed, whitespace and missing values normalized, lists parsed and de-duplicated, spelling fixes applied, values put into one standard format, types converted where every value converts cleanly, and a state corrected where its PIN and city both name another state (see ADR 0001). Values it cannot fix are left untouched, and flagged where the pincode directory disagrees, for Silver facilities.
_Avoid_: stage 1 table, silver v1

**Silver facilities**:
The second, final Silver stage, which resolves the nuanced, column-specific issues that Silver base leaves alone. All later work reads from it.
_Avoid_: silver stage 2, cleaned facilities

**Gold**:
The layer where facilities are evaluated by the quality of their data, including trust scores, evidence weighting and interpretation of content.
_Avoid_: final table, analysis table

**Inferred value**:
A value filled in from other columns or tables where the source stated none; only created in Gold, and always marked as unverified. Correcting a stated value that other source values agree is wrong (a state from its PIN and city) is a fix, not an Inferred value.
_Avoid_: imputed value, derived value

**Source tables**:
The three Virtue Foundation tables the project uses: facilities, the India Post pincode directory and the NFHS-5 district health indicators. No other data is used.
_Avoid_: raw data, CSV

### Facilities

**Facility**:
One real-world healthcare provider, identified by its `unique_id`.
_Avoid_: record, row, hospital (a hospital is one facility type)

**Exact duplicate**:
Two rows that are identical in every column; one copy is kept.
_Avoid_: duplicate (on its own, since same-name facilities are not duplicates)

**Duplicate item**:
Two items in the same list that are equal once case, spacing, punctuation and a trailing "s" are ignored; the first spelling is kept. Items differing by real letters (IUI vs IVF) are never duplicate items.
_Avoid_: typo, near-duplicate

**Description fragment**:
A row that is a broken-off piece of another facility's multi-line description rather than a facility; removed entirely in Silver.
_Avoid_: junk row, bad row

**Spelling fix**:
Replacing a variant way of writing a value (typo, abbreviation, old name, synonym, British spelling) with its one canonical form, e.g. farmacy to pharmacy or Orissa to Odisha.
_Avoid_: value mapping, inference

**Invalid value**:
A value that is not a valid value for its column at all, such as a city in the state field; never repaired by a spelling fix.
_Avoid_: typo, wrong value

**Missing value**:
A value that carries no information, whatever its original spelling (`"null"`, `""`, `"[]"`, or a list left empty after cleanup); always stored as a real NULL.
_Avoid_: blank, empty, "null"

**Truncated list**:
A list value that hit the source's 50-item cap, so some items were lost upstream and cannot be recovered from this dataset.
_Avoid_: full list, capped list

**Needs investigation**:
A facility with at least one truncated list, whose content must be treated as incomplete when it is evaluated.
_Avoid_: suspicious, low quality
