"""`confidence_citations`: the facility text behind every fired rule (spec #37).

The submission must cite the underlying facility text for any score. Each
citation is `{rule, field, item_id, text}`: the Gold rule it backs, the Silver
column it comes from, its `gold_facility_items` id when it is one of that table's
claims, and the text verbatim.

Two kinds of rule:
- A value rule compares fields, so its fields are its evidence: `CITED_FIELDS`
  names them, and every value is cited (one citation per list entry).
- A text rule (Stage 3 C2-C5) matched a few items of a long list. Only Stage 3
  knows which, so the items come from its `evidence_items` (`EVIDENCE_RULES`).
A rule about missing information (`NOTHING_TO_CITE`) has no text to cite; its
log line says what is missing.
"""

from pyspark.sql import Column
from pyspark.sql import functions as F

from talaria.gold import columns, scoring

CITATION_TYPE = columns.GOLD_FACILITIES["confidence_citations"]

# Gold rule -> the Silver Stage 3 columns whose values back it.
CITED_FIELDS = {
    "flag_coords_far_from_written_pin": ["latitude", "longitude", "address_pincode"],
    "flag_no_same_prefix_pin_nearby": ["latitude", "longitude", "address_pincode"],
    "flag_address_conflict": ["address_state", "address_city", "address_pincode"],
    "flag_pin_mismatch": ["address_state", "address_pincode"],
    "flag_pin_unverified": ["address_pincode"],
    "flag_name_facilityType": ["name", "facility_type"],
    # Stage 2 doesn't record which state name matched, so the whole description is cited.
    "flag_desc_mentions_other_state": ["address_state", "description"],
    "flag_coords_shared": ["latitude", "longitude"],
    "flag_affiliation_operator_conflict": ["affiliation_types", "operator_type"],
    "flag_facility_capacity_outlier": ["facility_type", "bed_count", "number_doctors"],
    "flag_official_phone_not_in_list": ["official_phone", "phone_numbers"],
    "flag_official_website_not_in_list": ["official_website", "websites"],
    "flag_only_directory_sources": ["source_urls"],
    "hospital_with_one_doctor": ["number_doctors"],
    "flag_state_corrected": ["address_state", "address_city", "address_pincode"],
    "flag_zero_beds": ["bed_count"],
    "flag_phone_list_without_official": ["phone_numbers"],
    "flag_single_source_domain": ["source_urls"],
    "flag_page_update_unparsable": ["recency_of_page_update"],
    "flag_future_page_update": ["recency_of_page_update"],
    "needs_investigation": ["truncated_columns"],
    "flag_has_government_source": ["source_urls"],
    "flag_own_site_in_sources": ["official_website", "source_urls"],
    "flag_large_hospital": ["facility_type", "bed_count", "number_doctors"],
}

# Gold rule -> the Stage 3 rule whose `evidence_items` back it.
EVIDENCE_RULES = {
    "flag_partial": "C2",
    "flag_specialty_unsupported": "C3",
    "flag_major_orphan": "C4",
    "flag_merge_different": "C5",
}

# Rules about missing information: nothing in the record to quote.
NOTHING_TO_CITE = {"no_sources", "flag_unverified"}


def _none() -> Column:
    return F.array().cast(CITATION_TYPE)


def _citation(rule: str, field: str, item_id: Column, text: Column) -> Column:
    return F.struct(
        F.lit(rule).alias("rule"),
        F.lit(field).alias("field"),
        item_id.cast("string").alias("item_id"),
        text.cast("string").alias("text"),
    )


def _item_id(item_type: str, position: Column) -> Column:
    """The `gold_facility_items` id of the claim at `position` (0-based) of its list."""
    return F.concat_ws(":", F.col("unique_id"), F.lit(item_type), position.cast("string"))


def _field_citations(rule: str, field: str, types: dict[str, str]) -> Column:
    """Every value of `field`: one citation per list entry, linked to its item when it is a claim."""
    value = F.col(field)
    no_id = F.lit(None).cast("string")
    if field in columns.LIST_ITEM_TYPES:
        item_type = columns.LIST_ITEM_TYPES[field]
        cited = F.transform(value, lambda text, i: _citation(rule, field, _item_id(item_type, i), text))
    elif types[field].startswith("array"):
        cited = F.transform(value, lambda text: _citation(rule, field, no_id, text))
    else:
        cited = F.array(_citation(rule, field, no_id, value))
    return F.coalesce(F.filter(cited, lambda citation: citation["text"].isNotNull()), _none())


def _position(values: Column, value: Column) -> Column:
    """The 0-based position of the first `value` in `values` (`array_position` takes only literals here)."""
    indexed = F.transform(values, lambda text, i: F.struct(text.alias("text"), i.alias("i")))
    return F.try_element_at(F.filter(indexed, lambda entry: entry["text"] == value), F.lit(1))["i"]


def _evidence_citations(rule: str, stage3_rule: str) -> Column:
    """The items Stage 3 matched for `stage3_rule`, linked to their claims."""

    def item_id(evidence: Column) -> Column:
        linked = F.lit(None).cast("string")
        for field, item_type in columns.LIST_ITEM_TYPES.items():
            position = _position(F.col(field), evidence["item"])
            linked = F.when(evidence["field"] == field, _item_id(item_type, position)).otherwise(linked)
        return linked

    evidence = F.filter(F.coalesce(F.col("evidence_items"), F.array()), lambda e: e["rule"] == stage3_rule)
    cited = F.transform(
        evidence,
        lambda e: F.struct(
            F.lit(rule).alias("rule"), e["field"].alias("field"), item_id(e).alias("item_id"), e["item"].alias("text")
        ),
    )
    return F.coalesce(cited.cast(CITATION_TYPE), _none())


def citations_column(types: dict[str, str]) -> Column:
    """`confidence_citations` over Silver Stage 3, in `scoring.RULES` order; `types` is its dtypes."""
    parts = []
    for rule in scoring.RULES:
        if rule.name in EVIDENCE_RULES:
            cited = _evidence_citations(rule.name, EVIDENCE_RULES[rule.name])
        elif rule.name in CITED_FIELDS:
            cited = F.concat(*[_field_citations(rule.name, field, types) for field in CITED_FIELDS[rule.name]])
        else:
            continue
        parts.append(F.when(rule.fired(), cited).otherwise(_none()))
    return F.concat(*parts) if parts else _none()

