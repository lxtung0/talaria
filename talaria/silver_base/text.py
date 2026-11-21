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


def null_if_missing(col: Column, *, placeholder_anywhere: bool = True) -> Column:
    """NULL for a Missing value: `null` (any case), `""`, `[]`, or the hidden-email placeholder.

    Expects whitespace-normalized input. With `placeholder_anywhere`, a value that
    merely contains the placeholder is Missing; without it, only a value that is
    exactly the placeholder is (for raw list text, where #4 judges each item).
    """
    placeholder = col.contains(_EMAIL_PLACEHOLDER) if placeholder_anywhere else col == _EMAIL_PLACEHOLDER
    missing = (F.lower(col) == "null") | (col == "") | (col == "[]") | placeholder
    return F.when(missing, F.lit(None).cast("string")).otherwise(col)


def clean_text(col: Column, *, placeholder_anywhere: bool = True) -> Column:
    """Whitespace normalization, then Missing values to NULL: the full rule for one text value."""
    return null_if_missing(normalize_whitespace(col), placeholder_anywhere=placeholder_anywhere)
