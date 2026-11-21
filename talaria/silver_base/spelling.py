"""Spelling fix rules for Silver base (spec #1, "Spelling fixes").

Each rule takes and returns one text value as a Spark `Column`, so it applies to a
plain column or, inside `F.transform`, to every list item. The alias data lives
in `aliases.py`.
"""

from collections.abc import Callable

from pyspark.sql import Column
from pyspark.sql import functions as F

from talaria.silver_base import aliases


def _lookup(table: dict[str, str], key: Column) -> Column:
    """The table's canonical value for `key`, or NULL when `key` is not an alias."""
    return F.create_map(*[F.lit(x) for pair in table.items() for x in pair])[key]


def _lower_case_with_aliases(table: dict[str, str]) -> Callable[[Column], Column]:
    """A rule for a lower-case column: lower-case the value, then replace it if it is an alias."""

    def rule(col: Column) -> Column:
        lowered = F.lower(col)
        return F.coalesce(_lookup(table, lowered), lowered)

    return rule


facility_type = _lower_case_with_aliases(aliases.FACILITY_TYPE)
operator_type = _lower_case_with_aliases(aliases.OPERATOR_TYPE)
affiliation_type = _lower_case_with_aliases(aliases.AFFILIATION_TYPE)


_SPECIALTY_REPLACEMENTS = [
    (shape(british), shape(american))
    for british, american in aliases.SPECIALTY_SPELLING.items()
    for shape in (str.lower, str.capitalize, str.upper)
]


def specialty(col: Column) -> Column:
    """British spelling fragments to American, keeping each fragment's case shape."""
    for british, american in _SPECIALTY_REPLACEMENTS:
        col = F.regexp_replace(col, british, american)
    return col


def city(col: Column) -> Column:
    """Title Case, then an old city name becomes its current one (`Bangalore` -> `Bengaluru`)."""
    return F.coalesce(_lookup(aliases.CITY, F.lower(col)), F.initcap(col))


# Official names (any case) and their aliases, lower-case -> official name.
_STATE_LOOKUP = {name.lower(): name for name in aliases.OFFICIAL_STATES} | aliases.STATE


def state(col: Column) -> Column:
    """An official name or alias becomes the official name; so does a value whose
    final comma-separated part is one (`Gurugram, Haryana` -> `Haryana`).
    Anything else is unchanged."""
    whole = _lookup(_STATE_LOOKUP, F.lower(col))
    after_last_comma = _lookup(_STATE_LOOKUP, F.lower(F.trim(F.element_at(F.split(col, ","), -1))))
    return F.coalesce(whole, F.when(col.contains(","), after_last_comma), col)
