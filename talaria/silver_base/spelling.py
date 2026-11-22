"""Spelling fix rules for Silver base (spec #1, "Spelling fixes").

Each rule takes and returns one text value as a Spark `Column`, so it applies to a
plain column or, inside `F.transform`, to every list item. The alias data lives
in `aliases.py`.
"""

import json
from collections.abc import Callable

from pyspark.sql import Column
from pyspark.sql import functions as F

from talaria.silver_base import aliases
from talaria.silver_base.text import lookup


def _lower_case_with_aliases(table: dict[str, str]) -> Callable[[Column], Column]:
    """A rule for a lower-case column: lower-case the value, then replace it if it is an alias."""

    def rule(col: Column) -> Column:
        lowered = F.lower(col)
        return F.coalesce(lookup(table, lowered), lowered)

    return rule


facility_type = _lower_case_with_aliases(aliases.FACILITY_TYPE)
operator_type = _lower_case_with_aliases(aliases.OPERATOR_TYPE)
affiliation_type = _lower_case_with_aliases(aliases.AFFILIATION_TYPE)


# (British, American) per fragment and case shape, in table order.
_AMERICAN_SPELLING_REPLACEMENTS = [
    (shape(british), shape(american))
    for british, american in aliases.BRITISH_SPELLING.items()
    for shape in (str.lower, str.capitalize, str.upper)
]
_AMERICAN_SPELLING_JSON = json.dumps([{"b": b, "a": a} for b, a in _AMERICAN_SPELLING_REPLACEMENTS])


def american_spelling(col: Column) -> Column:
    """British spelling fragments to American, in table order, keeping each fragment's case shape.

    One `aggregate` over the replacement pairs rather than a chain of nested
    replaces: hundreds of nested expressions overflow Spark's code generator.
    The pairs are one JSON literal (folded to a constant by Spark) rather than
    hundreds of literal columns, which are slow to build.
    """
    pairs = F.from_json(F.lit(_AMERICAN_SPELLING_JSON), "array<struct<b: string, a: string>>")
    return F.aggregate(pairs, col, lambda acc, pair: F.replace(acc, pair["b"], pair["a"]))


def city(col: Column) -> Column:
    """Title Case, then an old city name becomes its current one (`Bangalore` -> `Bengaluru`)."""
    return F.coalesce(lookup(aliases.CITY, F.lower(col)), F.initcap(col))


_OFFICIAL_STATE_LOOKUP = {name.lower(): name for name in aliases.OFFICIAL_STATES}
# Official names (any case) and their aliases, lower-case -> official name.
_STATE_LOOKUP = _OFFICIAL_STATE_LOOKUP | aliases.STATE


def official_state(col: Column) -> Column:
    """The official state name for a value that is one in any case (`TAMIL NADU`), NULL otherwise.

    No aliases: the pincode directory's `NA` and an unfixed Facility state are both NULL.
    """
    return lookup(_OFFICIAL_STATE_LOOKUP, F.lower(F.trim(col)))


def state(col: Column) -> Column:
    """An official name or alias becomes the official name; so does a value whose
    final comma-separated part is one (`Gurugram, Haryana` -> `Haryana`).
    Anything else is unchanged."""
    whole = lookup(_STATE_LOOKUP, F.lower(col))
    after_last_comma = lookup(_STATE_LOOKUP, F.lower(F.trim(F.element_at(F.split(col, ","), -1))))
    return F.coalesce(whole, F.when(col.contains(","), after_last_comma), col)
