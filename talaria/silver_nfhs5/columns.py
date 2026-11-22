"""Which NFHS-5 columns are which (#41). Every column not named here is an indicator."""

# Together they name one district; `district_name` alone repeats across states.
STATE = "state_ut"
DISTRICT = "district_name"
KEY = [STATE, DISTRICT]

# How many households and people were surveyed in the district: whole numbers.
SURVEY_SIZES = ["households_surveyed", "women_15_49_interviewed", "men_15_54_interviewed"]

# Load metadata added by the bronze ingest, kept as it is.
METADATA = ["_source_table", "_ingested_at"]

# New columns, after the source's: which indicators carried which NFHS-5 marker.
SUPPRESSED = "suppressed_columns"  # `*`: fewer than 25 unweighted cases, no value
LOW_SAMPLE = "low_sample_columns"  # `(x)`: 25-49 unweighted cases, less reliable
NEW_COLUMNS = {SUPPRESSED: "array<string>", LOW_SAMPLE: "array<string>"}


def indicators(columns: list[str]) -> list[str]:
    """The indicator columns of a bronze NFHS-5 table, in source order."""
    named = {*KEY, *SURVEY_SIZES, *METADATA}
    return [name for name in columns if name not in named]
