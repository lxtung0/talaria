"""The columns Silver facilities adds to Silver base (spec #13, "New columns").

The one home for this list: `pipeline` selects these columns, `checks` checks
them and `flag_counts` counts the flags, so a new column is one entry here plus
its rule. Kept in the spec's order, which is also the output column order.
"""

from dataclasses import dataclass

FLAG_TYPE = "boolean"


@dataclass(frozen=True)
class NewColumn:
    """`group` is the spec's letter; `type` is the Spark type's simple string."""

    name: str
    group: str
    type: str = FLAG_TYPE


NEW_COLUMNS = [
    # E. Affiliation. `primary_affiliation` is the one value column, and the one that can be NULL.
    NewColumn("flag_affiliation_operator_conflict", "E"),
    NewColumn("primary_affiliation", "E", "string"),
    # G. Page update date.
    NewColumn("flag_page_update_unparsable", "G"),
    NewColumn("flag_future_page_update", "G"),
]


def flags() -> list[NewColumn]:
    """The new flag columns: boolean and never NULL."""
    return [column for column in NEW_COLUMNS if column.type == FLAG_TYPE]
