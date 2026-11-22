"""Group E, affiliation (spec #13, #18): `primary_affiliation` and the operator conflict flag.

Silver base keeps each affiliation once, so the counts come from the raw
`affiliationTypeIds` list in bronze, cleaned item by item with Silver base's own
rules. A raw item counts toward the Silver base value it was deduplicated into.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_base import columns as base_columns
from talaria.silver_base.text import clean_item, clean_list_text, text_item_key

# D2: ties go to the value listed first. These are also the allowed values: any of
# them beats an Invalid value (`naac`, `dci`, ...), however often that appears (#18).
RANK = ["government", "academic", "faith-tradition", "philanthropy-legacy", "community", "corporate", "private", "public"]

_RAW = "affiliationTypeIds"
_RAW_KEYS = "_affiliation_raw_keys"


def add_columns(df: DataFrame, bronze: DataFrame) -> DataFrame:
    affiliations, operator = F.col("affiliation_types"), F.col("operator_type")
    conflict = (F.array_contains(affiliations, "government") & (operator == "private")) | (
        (F.array_contains(affiliations, "private") | F.array_contains(affiliations, "corporate"))
        & (operator == "public")
    )
    return (
        df.join(_raw_keys(bronze), "unique_id", "left")
        .withColumns(
            {
                "flag_affiliation_operator_conflict": F.coalesce(conflict, F.lit(False)),
                "primary_affiliation": _primary(affiliations, F.col(_RAW_KEYS)),
            }
        )
        .drop(_RAW_KEYS)
    )


def _raw_keys(bronze: DataFrame) -> DataFrame:
    """`unique_id` and the Duplicate-item key of every raw affiliation item, repeats kept.

    The same rows Silver base keeps (no Description fragments, exact duplicates
    collapsed), and each item cleaned as Silver base cleans it before deduplicating.
    """
    rows = bronze.where(~base_columns.is_description_fragment()).dropDuplicates()
    items = F.transform(base_columns.parse_list(clean_list_text(F.col(_RAW))), clean_item)
    fixed = F.transform(items, base_columns.SPELLING_FIXES["affiliation_type"].fix)
    keys = F.transform(F.filter(fixed, lambda item: item.isNotNull()), text_item_key)
    return rows.select("unique_id", keys.alias(_RAW_KEYS))


def _primary(affiliations: Column, raw_keys: Column) -> Column:
    """The Silver base value with the best (allowed, count, D2 rank, name); NULL when there are none.

    Struct fields compare in order, so the smallest struct wins: allowed before
    Invalid, then the highest count, then D2 order, then alphabetical (Invalid only).
    """
    rank = F.create_map(*[F.lit(x) for i, value in enumerate(RANK) for x in (value, i)])

    def score(value: Column) -> Column:
        count = F.size(F.filter(raw_keys, lambda key: key == text_item_key(value)))
        position = rank[value]
        return F.struct(
            position.isNull().alias("invalid"),
            (-count).alias("count"),
            F.coalesce(position, F.lit(len(RANK))).alias("rank"),
            value.alias("value"),
        )

    return F.array_min(F.transform(affiliations, score))["value"]
