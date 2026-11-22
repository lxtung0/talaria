"""The reference tables Silver Stage 3 matches against (#35, "Reference tables").

They are CSVs in `reference/` next to this module, reviewed like code, and the only
source for Stage 3's mappings and patterns. Every regex already starts with `(?i)`
and is written for Java regex (Spark `RLIKE`). See ADR 0003.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

REFERENCE_DIR = Path(__file__).parent / "reference"


@dataclass(frozen=True)
class ProcedureEquipmentRule:
    """Rule C2: a service that needs both a procedure and equipment to back each other."""

    service: str
    procedure_regex: str
    equipment_regex: str
    check_forward: bool
    check_reverse: bool


@dataclass(frozen=True)
class References:
    # specialty_category_map_v3: specialty code -> category.
    specialty_categories: dict[str, str]
    # ref_text_category_keywords: category -> regex detecting it in free text.
    text_category_regex: dict[str, str]
    # ref_related_categories: category -> categories that also count as a match for it.
    related_categories: dict[str, list[str]]
    # ref_procedure_equipment_rules.
    procedure_equipment_rules: list[ProcedureEquipmentRule]
    # ref_capability_units: unit -> (capability regex, categories supporting it).
    capability_units: dict[str, tuple[str, list[str]]]
    # ref_high_risk_categories: category -> specialty categories accepted for it.
    high_risk_categories: dict[str, list[str]]


def load_references(directory: Path = REFERENCE_DIR) -> References:
    """Read the six reference CSVs."""

    def rows(name: str) -> list[dict[str, str]]:
        with open(Path(directory) / f"{name}.csv", newline="", encoding="utf-8") as file:
            return [{key: value.strip() for key, value in row.items()} for row in csv.DictReader(file)]

    def pipe_list(text: str) -> list[str]:
        return [item.strip() for item in text.split("|") if item.strip()]

    related: dict[str, list[str]] = {}
    for row in rows("ref_related_categories"):
        related.setdefault(row["category"], []).append(row["related_category"])

    return References(
        specialty_categories={row["specialty_code"]: row["category"] for row in rows("specialty_category_map_v3")},
        text_category_regex={row["category"]: row["text_regex"] for row in rows("ref_text_category_keywords")},
        related_categories=related,
        procedure_equipment_rules=[
            ProcedureEquipmentRule(
                row["service"],
                row["procedure_regex"],
                row["equipment_regex"],
                row["check_forward"].lower() == "true",
                row["check_reverse"].lower() == "true",
            )
            for row in rows("ref_procedure_equipment_rules")
        ],
        capability_units={
            row["unit"]: (row["capability_regex"], pipe_list(row["supporting_categories"]))
            for row in rows("ref_capability_units")
        },
        high_risk_categories={
            row["high_risk_category"]: pipe_list(row["accepted_related_specialty_categories"])
            for row in rows("ref_high_risk_categories")
        },
    )
