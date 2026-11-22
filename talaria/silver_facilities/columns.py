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
    # A. Contact consistency.
    NewColumn("flag_official_phone_not_in_list", "A"),
    NewColumn("flag_phone_list_without_official", "A"),
    NewColumn("flag_official_website_not_in_list", "A"),
    # B. Size consistency.
    NewColumn("flag_bed_doctor_ratio_outlier", "B"),
    # E. Affiliation. `primary_affiliation` is the one value column, and the one that can be NULL.
    NewColumn("flag_affiliation_operator_conflict", "E"),
    NewColumn("primary_affiliation", "E", "string"),
    # G. Page update date.
    NewColumn("flag_page_update_unparsable", "G"),
    NewColumn("flag_future_page_update", "G"),
    # H. Location: only Facilities with a Silver base location flag are checked.
    NewColumn("flag_coords_far_from_written_pin", "H"),
    NewColumn("flag_no_same_prefix_pin_nearby", "H"),
    NewColumn("flag_coords_shared", "H"),
]


def flags() -> list[NewColumn]:
    """The new flag columns: boolean and never NULL."""
    return [column for column in NEW_COLUMNS if column.type == FLAG_TYPE]
