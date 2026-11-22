"""Group C, specialty consistency (spec #13, #17).

`flag_specialty_unsupported_by_capability` is true when none of a Facility's
specialties is backed by any `capability` sentence, by its own words or by a
synonym of its group (`specialty_synonyms`). Which specialty or sentence matched
is never stored.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_facilities import words
from talaria.silver_facilities.specialty_synonyms import SPECIALTY_GROUPS

_TEXT = "_specialty_capability_text"
_TRUNCATED = ["specialties", "capability"]


def add_columns(df: DataFrame) -> DataFrame:
    text = F.col(_TEXT)
    # One working column per group: does any sentence name one of its synonyms?
    hits = {
        f"_specialty_group_{i}": text.rlike(words.any_pattern(group.synonyms))
        for i, group in enumerate(SPECIALTY_GROUPS)
    }
    truncated = F.coalesce(F.col("truncated_columns"), F.array().cast("array<string>"))
    checkable = (
        F.col("specialties").isNotNull()
        & F.col("capability").isNotNull()
        & ~F.exists(truncated, lambda name: name.isin(_TRUNCATED))
    )

    def backed(specialty: Column) -> Column:
        phrase = _code_words(specialty)
        own_words = F.regexp(text, words.phrase_pattern(phrase))
        by_group = [
            phrase.rlike(words.any_pattern(group.specialties)) & F.col(hit)
            for group, hit in zip(SPECIALTY_GROUPS, hits)
        ]
        return own_words | _any(by_group)

    unsupported = ~F.exists(F.col("specialties"), backed)
    return (
        df.withColumn(_TEXT, F.lower(F.array_join(F.col("capability"), "\n")))
        .withColumns(hits)
        .withColumn("flag_specialty_unsupported_by_capability", F.when(checkable, unsupported).otherwise(F.lit(False)))
        .drop(_TEXT, *hits)
    )


def _code_words(code: Column) -> Column:
    """`internalMedicine` -> `internal medicine`: a space before each capital that follows a lower-case letter."""
    return F.lower(F.regexp_replace(code, r"(\p{Ll})(\p{Lu})", "$1 $2"))


def _any(conditions: list[Column]) -> Column:
    result = F.lit(False)
    for condition in conditions:
        result = result | condition
    return result
