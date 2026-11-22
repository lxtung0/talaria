"""The Stage 3 rule log and the replaced-flag cross-tabs, for the notebook (#35, "Outputs")."""

from dataclasses import dataclass

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_stage3 import columns
from talaria.silver_stage3.large_hospital import steps


@dataclass(frozen=True)
class Rule:
    rule_id: str
    output_column: str
    # Rows the rule flags or, for R2-R5, rows still in the large hospital funnel after it.
    counted: Column


def _remaining_after(step: str) -> Column:
    """Rows that passed `step` and every step before it."""
    failed_by_now = list(steps())[: list(steps()).index(step) + 1]
    failed = F.col("large_hospital_step_failed")
    return failed.isNull() | ~failed.isin(*failed_by_now)


def rules() -> list[Rule]:
    reason = F.coalesce(F.col("outlier_reason"), F.lit(""))
    return [
        Rule("R0", "flag_facility_capacity_outlier", F.col("flag_facility_capacity_outlier")),
        *[Rule(f"R0-{i}", "outlier_reason", reason.contains(f"R0-{i}")) for i in range(1, 7)],
        Rule("F1", "flag_name_facilityType", F.col("flag_name_facilityType")),
        Rule("R1", "is_veterinary", F.col("is_veterinary")),
        *[Rule(step, "large_hospital_step_failed", _remaining_after(step)) for step in ["R2", "R3", "R4", "R5"]],
        Rule("C1", "flag_unverified", F.col("flag_unverified")),
        Rule("C2", "flag_partial", F.col("flag_partial")),
        Rule("C3", "flag_specialty_unsupported", F.col("flag_specialty_unsupported")),
        Rule("C4", "flag_major_orphan", F.col("flag_major_orphan")),
        Rule("C5", "flag_merge_different", F.col("flag_merge_different")),
    ]


def rule_counts(stage3: DataFrame) -> DataFrame:
    """One row per rule: `rule_id`, `output_column`, `rows_flagged_or_remaining`, in one Spark job."""
    all_rules = rules()
    row = stage3.agg(*[F.count(F.when(rule.counted, 1)).alias(rule.rule_id) for rule in all_rules]).first()
    return stage3.sparkSession.createDataFrame(
        [(rule.rule_id, rule.output_column, row[rule.rule_id]) for rule in all_rules],
        "rule_id string, output_column string, rows_flagged_or_remaining long",
    )


def replaced_flag_crosstabs(silver_facilities: DataFrame, stage3: DataFrame) -> dict[str, DataFrame]:
    """For each dropped Stage 2 flag, its counts against the Stage 3 flag replacing it."""
    joined = silver_facilities.select("unique_id", *columns.REPLACED_COLUMNS).join(
        stage3.select("unique_id", *columns.REPLACED_COLUMNS.values()), "unique_id"
    )
    return {
        old: joined.groupBy(old, new).count().orderBy(old, new)
        for old, new in columns.REPLACED_COLUMNS.items()
    }
