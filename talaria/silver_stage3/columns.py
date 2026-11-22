"""The columns Silver Stage 3 drops from and adds to Silver facilities (#35).

The one home for these lists: `pipeline` selects them, `checks` checks them and
`rule_counts` counts them. Kept in #35's step order, which is also the output order.
"""

from dataclasses import dataclass

FLAG_TYPE = "boolean"

# Stage 2 flags checking the same problem as a Stage 3 rule, more narrowly. Dropped so
# one issue is never flagged twice: {Stage 2 flag: the Stage 3 flag replacing it}.
REPLACED_COLUMNS = {
    "flag_bed_doctor_ratio_outlier": "flag_facility_capacity_outlier",
    "flag_specialty_unsupported_by_capability": "flag_specialty_unsupported",
}


@dataclass(frozen=True)
class NewColumn:
    """`step` is #35's step or rule; `type` is the Spark type's simple string."""

    name: str
    step: str
    type: str = FLAG_TYPE


NEW_COLUMNS = [
    # Step 1. Specialty categories.
    NewColumn("specialty_categories", "1", "array<string>"),
    NewColumn("n_specialty_categories", "1", "int"),
    NewColumn("core_categories", "1", "array<string>"),
    # Step 2. R0, capacity outliers.
    NewColumn("flag_facility_capacity_outlier", "R0"),
    NewColumn("outlier_reason", "R0", "string"),
    NewColumn("bed_outlier", "R0"),
    NewColumn("doctor_outlier", "R0"),
    # Step 3. F1, name vs facility type.
    NewColumn("flag_name_facilityType", "F1"),
    # Step 4. R1-R5, large hospital.
    NewColumn("is_veterinary", "R1"),
    NewColumn("flag_large_hospital", "R5"),
    NewColumn("large_hospital_step_failed", "R5", "string"),
    # Step 5. C1-C5, consistency.
    NewColumn("flag_unverified", "C1"),
    NewColumn("unverified_reason", "C1", "string"),
    NewColumn("flag_partial", "C2"),
    NewColumn("partial_reason", "C2", "string"),
    NewColumn("flag_specialty_unsupported", "C3"),
    NewColumn("unsupported_specialty_share", "C3", "double"),
    NewColumn("unsupported_specialties", "C3", "array<string>"),
    NewColumn("flag_major_orphan", "C4"),
    NewColumn("orphan_reason", "C4", "string"),
    NewColumn("flag_merge_different", "C5"),
]


def flags() -> list[NewColumn]:
    """The new boolean columns: never NULL."""
    return [column for column in NEW_COLUMNS if column.type == FLAG_TYPE]
