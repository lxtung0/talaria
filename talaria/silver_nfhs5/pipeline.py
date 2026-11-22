"""The Silver NFHS-5 pipeline (#41): trim, official state names, typed values, markers."""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_base import spelling
from talaria.silver_nfhs5 import columns

# State spellings NFHS-5 uses that the Silver base state aliases don't cover.
STATE_ALIASES = {"maharastra": "Maharashtra"}

NUMBER = r"^-?\d+(\.\d+)?$"
# A whole number, also as a `double` column reads as text (`882.0`).
WHOLE_NUMBER = r"^-?\d+(\.0+)?$"
LOW_SAMPLE_VALUE = r"^\((.*)\)$"


def trimmed(name: str) -> Column:
    """The value as trimmed text; blank becomes NULL."""
    text = F.trim(F.col(f"`{name}`").cast("string"))
    return F.when(text != "", text)


def state(raw: Column) -> Column:
    """The official state name, or NULL when the value names none.

    `&` reads as `and`, then the Silver base state rules apply (`NCT of Delhi` ->
    `Delhi`), then `STATE_ALIASES`.
    """
    text = F.regexp_replace(F.trim(raw), r"\s*&\s*", " and ")
    fixed = spelling.state(text)
    for alias, official in STATE_ALIASES.items():
        fixed = F.when(F.lower(text) == alias, F.lit(official)).otherwise(fixed)
    return spelling.official_state(fixed)


def district(raw: Column) -> Column:
    """Trimmed, inner whitespace collapsed; otherwise as written."""
    return F.regexp_replace(F.trim(raw), r"\s+", " ")


def _number(text: Column, kind: str) -> Column:
    """`text` as `kind` when it is a plain number, NULL otherwise (the runtime checks catch it)."""
    return F.when(text.rlike(NUMBER), text.cast(kind))


def _whole_number(text: Column) -> Column:
    """`text` as `int` when it is a whole number, NULL otherwise (the runtime checks catch it)."""
    return F.when(text.rlike(WHOLE_NUMBER), text.cast("double").cast("int"))


def _indicator(name: str) -> tuple[Column, Column, Column]:
    """(value, suppressed, low sample) for one indicator."""
    text = trimmed(name)
    suppressed = F.coalesce(text == "*", F.lit(False))
    low_sample = F.coalesce(text.rlike(LOW_SAMPLE_VALUE), F.lit(False))
    number = F.when(low_sample, F.trim(F.regexp_extract(text, LOW_SAMPLE_VALUE, 1))).otherwise(text)
    return F.when(~suppressed, _number(number, "double")), suppressed, low_sample


def _named_when(conditions: dict[str, Column]) -> Column:
    """The names whose condition is true, in order; NULL when none is."""
    names = F.array_compact(F.array(*[F.when(c, F.lit(n)) for n, c in conditions.items()]))
    return F.when(F.size(names) > 0, names)


def build_silver_nfhs5(bronze: DataFrame) -> DataFrame:
    """One row per district: every source column, cleaned, then `columns.NEW_COLUMNS`.

    Values are only trimmed, retyped and unwrapped from their marker; nothing is
    filled in or renamed. A value that won't parse becomes NULL, and
    `checks.check_silver_nfhs5` fails the run on it.
    """
    indicators = columns.indicators(bronze.columns)
    parsed = {name: _indicator(name) for name in indicators}

    selected = []
    for name in bronze.columns:
        if name == columns.STATE:
            selected.append(state(F.col(name)).alias(name))
        elif name == columns.DISTRICT:
            selected.append(district(F.col(name)).alias(name))
        elif name in columns.SURVEY_SIZES:
            selected.append(_whole_number(trimmed(name)).alias(name))
        elif name in parsed:
            selected.append(parsed[name][0].alias(name))
        else:
            selected.append(F.col(f"`{name}`"))
    selected.append(_named_when({n: s for n, (_, s, _) in parsed.items()}).alias(columns.SUPPRESSED))
    selected.append(_named_when({n: low for n, (_, _, low) in parsed.items()}).alias(columns.LOW_SAMPLE))
    return bronze.select(*selected)
