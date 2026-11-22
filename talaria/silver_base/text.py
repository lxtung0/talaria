"""Column-level text rules shared by Silver base steps (spec #1, Whitespace and Missing values).

Each function takes and returns a Spark `Column`, so the same rule applies to a
whole text column or, inside `F.transform`, to every item of a list column.
"""

from pyspark.sql import Column
from pyspark.sql import functions as F

# Every kind of whitespace the source uses: Java's \s (space, tab, newlines, ...)
# plus the Unicode spaces it misses, including non-breaking (U+00A0, U+2007,
# U+202F), zero-width (U+200B) and the byte-order mark (U+FEFF).
_WHITESPACE = r"[\s  ᠎ -​    　﻿]"

# The hidden-email placeholder left by the source's email obfuscation.
_EMAIL_PLACEHOLDER = "[email protected]"


def normalize_whitespace(col: Column) -> Column:
    """Trim every kind of whitespace from both ends and collapse inner runs to one space."""
    trimmed = F.regexp_replace(col, rf"^{_WHITESPACE}+|{_WHITESPACE}+$", "")
    return F.regexp_replace(trimmed, rf"{_WHITESPACE}+", " ")


def _without_placeholder(col: Column) -> Column:
    return normalize_whitespace(F.replace(col, F.lit(_EMAIL_PLACEHOLDER), F.lit("")))


def missing_spelling(col: Column) -> Column:
    """Which Missing value a whitespace-normalized value is, or NULL when it is not one.

    `hidden_email` when nothing but the hidden-email placeholder is left once it is
    cut out; otherwise `null_text` (any case), `empty_text` or `empty_array_text`
    for what is left.
    """
    rest = _without_placeholder(col)
    return (
        F.when(col.contains(_EMAIL_PLACEHOLDER) & (rest == ""), "hidden_email")
        .when(F.lower(rest) == "null", "null_text")
        .when(rest == "", "empty_text")
        .when(rest == "[]", "empty_array_text")
    )


def clean_text(col: Column) -> Column:
    """The full rule for one plain text value: whitespace normalized, the hidden-email
    placeholder cut out, and a Missing value made NULL."""
    value = normalize_whitespace(col)
    return F.when(missing_spelling(value).isNull(), _without_placeholder(value))


def clean_item(col: Column) -> Column:
    """The rule for one list item: whitespace normalized; NULL when it is a Missing
    value or holds the hidden-email placeholder at all (the item is dropped later)."""
    value = normalize_whitespace(col)
    return F.when(missing_spelling(value).isNull() & ~value.contains(_EMAIL_PLACEHOLDER), value)


def clean_list_text(col: Column) -> Column:
    """The rule for a list column's raw text, before it is parsed: whitespace normalized,
    a Missing value made NULL. The placeholder inside it is left for `clean_item`."""
    value = normalize_whitespace(col)
    return F.when(missing_spelling(value).isNull(), value)


def lookup(table: dict[str, str], key: Column) -> Column:
    """The table's value for `key`, or NULL when `key` is not in it."""
    return F.create_map(*[F.lit(x) for pair in table.items() for x in pair])[key]
