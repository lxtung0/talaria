"""Whole-word text matching shared by the free-text flag groups (C and D, spec #13)."""

from pyspark.sql import Column
from pyspark.sql import functions as F

# Not a letter or digit on that side, so `ent` doesn't match inside `entire`. Java
# regex's `\b` is unreliable next to punctuation (`ent/`), so lookarounds are used.
_WORD_START = r"(?<![\p{L}\p{N}])"
_WORD_END = r"(?![\p{L}\p{N}])"


def word_pattern(term: str) -> str:
    """A Spark (Java) regex for `term` as whole words; a trailing `*` matches a word start only.

    Spaces in `term` match any run of whitespace. The words are quoted, so `24/7`
    or `de-addiction` match literally.
    """
    prefix = term.endswith("*")
    words = term.removesuffix("*").split()
    body = r"\s+".join(rf"\Q{word}\E" for word in words)
    return _WORD_START + body + ("" if prefix else _WORD_END)


def whole_words(pattern: str) -> str:
    """`pattern` (already a regex) matched as whole words only."""
    return _WORD_START + pattern + _WORD_END


def any_pattern(terms: list[str]) -> str:
    """A regex matching any of `terms` (see `word_pattern`)."""
    return "|".join(f"(?:{word_pattern(term)})" for term in terms)


def phrase_pattern(phrase: Column) -> Column:
    """A regex for the text in column `phrase`, quoted, as whole words."""
    return F.concat(F.lit(_WORD_START + r"\Q"), phrase, F.lit(r"\E" + _WORD_END))
