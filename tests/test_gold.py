"""Gold behaviour (spec #37), tested through `build_gold` on real Silver Stage 3 output."""

import datetime

import pytest
from pyspark.sql import functions as F

from talaria.gold import build_gold, scoring
from talaria.gold.checks import check_gold
from talaria.gold.score_counts import format_score_counts, score_counts
from talaria.silver_facilities import build_silver_facilities
from talaria.silver_stage3 import build_silver_stage3

RUN_DATE = datetime.date(2026, 11, 21)
FLAG_RULES = [rule for rule in scoring.RULES if rule.condition is None]
# Every boolean the rules read, so the fixture can start each Facility clean.
SCORED_FLAGS = [*[rule.name for rule in FLAG_RULES], "flag_facility_capacity_outlier", "is_veterinary"]


# Building Silver Stage 3 runs every earlier stage, so each distinct input is built once.
_BUILT = {}


@pytest.fixture
def silver(make_silver_inputs, no_pincodes):
    """Silver Stage 3 from partial bronze rows, with every scored flag set to false.

    Tests then turn on exactly the flags they mean, so the default fixture's own
    flags (a single source host, say) never leak into the score.
    """

    def build(*rows):
        key = repr(rows)
        if key not in _BUILT:
            _BUILT[key] = _build(*rows)
        return _BUILT[key]

    def _build(*rows):
        bronze, silver_base = make_silver_inputs(*rows)
        df = build_silver_stage3(build_silver_facilities(silver_base, bronze, no_pincodes, RUN_DATE))
        for name in SCORED_FLAGS:
            df = df.withColumn(name, F.lit(False))
        return df.localCheckpoint()

    return build


def gold_row(silver_df, **flags):
    for name, value in flags.items():
        silver_df = silver_df.withColumn(name, F.lit(value))
    facilities, _ = build_gold(silver_df)
    return facilities.first()


def test_no_flags_scores_the_start(silver):
    row = gold_row(silver({"name": "City Hospital"}))

    assert row.confidence_score == 0.80
    assert row.confidence_reasons == ["start 80"]
    assert row.location_uncertain is False


# One representative rule per tier; the rule table itself is reviewed in the ADR.
REPRESENTATIVE_RULES = [
    next(rule for rule in FLAG_RULES if rule.tier == tier.name) for tier in scoring.TIERS
]


@pytest.mark.parametrize("rule", REPRESENTATIVE_RULES, ids=lambda rule: rule.name)
def test_each_rule_adds_its_points_and_its_line(silver, rule):
    tier = scoring.TIER_BY_NAME[rule.tier]
    row = gold_row(silver({}), **{rule.name: True})

    points = 80 + tier.points
    expected = ["start 80", rule.line()]
    if tier.cap is not None and points > tier.cap:
        expected.append(f"cap {tier.cap} [{tier.name}]")
        points = tier.cap
    assert row.confidence_reasons == expected
    assert row.confidence_score == points / 100


def test_no_sources_is_critical(silver):
    df = silver({}).withColumn("source_urls", F.lit(None).cast("array<string>"))
    row = gold_row(df)

    assert row.confidence_reasons == ["start 80", "-20 [critical] No source pages are listed", "cap 55 [critical]"]
    assert row.confidence_score == 0.55


def test_positive_evidence_cannot_lift_past_the_worst_tiers_cap(silver):
    row = gold_row(
        silver({}),
        flag_only_directory_sources=True,
        flag_has_government_source=True,
        flag_own_site_in_sources=True,
    )

    assert row.confidence_reasons == [
        "start 80",
        "-10 [major] All sources are directory or social media listings",
        "+10 [positive] A government website is among the sources",
        "+10 [positive] The facility's own website is among the sources",
        "cap 75 [major]",
    ]
    assert row.confidence_score == 0.75


def test_both_positives_reach_full_marks(silver):
    row = gold_row(silver({}), flag_has_government_source=True, flag_own_site_in_sources=True)

    assert row.confidence_score == 1.0


def test_log_runs_worst_tier_first_and_a_lower_score_needs_no_cap_line(silver):
    row = gold_row(silver({}), needs_investigation=True, flag_pin_unverified=True, flag_address_conflict=True)

    assert row.confidence_reasons == [
        "start 80",
        "-20 [critical] The address names a state that its PIN code and city disagree with",
        "-20 [critical] The PIN code is not in the India Post directory",
        "-3 [minor] Some lists were cut off at 50 items, so the record may be incomplete",
    ]
    assert row.confidence_score == 0.37


def test_score_never_goes_below_zero(silver):
    critical = {rule.name: True for rule in scoring.rules_in("critical") if rule.condition is None}
    major = {rule.name: True for rule in scoring.rules_in("major")}
    row = gold_row(silver({}), **critical, **major)

    assert row.confidence_score == 0.0


def test_replaced_stage2_flags_are_not_read(silver):
    assert "flag_specialty_unsupported_by_capability" not in silver({}).columns


@pytest.mark.parametrize(
    "reason, expected",
    [
        ("R0-5", ["start 80", "-3 [minor] The doctor count of 1 for a hospital looks like a placeholder"]),
        ("R0-4; R0-5", ["start 80", "-10 [major] The bed or doctor count looks wrong for this facility"]),
    ],
)
def test_one_doctor_alone_is_minor_and_any_other_capacity_rule_is_major(silver, reason, expected):
    row = gold_row(silver({}), flag_facility_capacity_outlier=True, outlier_reason=reason)

    assert row.confidence_reasons == expected


def test_missing_information_is_logged_but_not_scored(silver):
    row = gold_row(silver({}), flag_unverified=True)

    assert row.confidence_reasons == ["start 80", "0 [info] Procedures, equipment or capabilities are not listed"]
    assert row.confidence_score == 0.80


def test_a_procedure_without_its_equipment_is_minor(silver):
    row = gold_row(silver({}), flag_partial=True)

    assert row.confidence_reasons == [
        "start 80",
        "-3 [minor] Some procedures are listed without matching equipment, or the reverse",
    ]
    assert row.confidence_score == 0.77


def test_three_positives_stop_at_full_marks(silver):
    row = gold_row(silver({}), flag_has_government_source=True, flag_own_site_in_sources=True, flag_large_hospital=True)

    assert row.confidence_score == 1.0


def test_veterinary_facilities_leave_both_tables(silver):
    df = silver({"unique_id": "pet", "specialties": '["cardiology"]'}, {"unique_id": "people"})
    df = df.withColumn("is_veterinary", F.col("unique_id") == "pet")

    facilities, items = build_gold(df)

    assert [row.unique_id for row in facilities.collect()] == ["people"]
    assert items.where(F.col("unique_id") == "pet").count() == 0
    check_gold(df, facilities, items)


@pytest.mark.parametrize("flag", ["flag_coords_shared"])
def test_any_group_h_flag_makes_location_uncertain(silver, flag):
    assert gold_row(silver({}), **{flag: True}).location_uncertain is True


def test_location_uncertain_ignores_silver_base_location_flags(silver):
    assert gold_row(silver({}), flag_pin_unverified=True).location_uncertain is False


def test_copies_silver_values_verbatim(silver):
    df = silver({"name": "City Hospital", "address_city": "Pune", "officialPhone": "98765 43210", "latitude": 18.5})
    facilities, _ = build_gold(df)
    gold, base = facilities.first(), df.first()

    for name in ["unique_id", "name", "address_city", "official_phone", "latitude", "source_urls", "needs_investigation"]:
        assert gold[name] == base[name]


def items_of(df):
    _, items = build_gold(df)
    return sorted((row.item_id, row.item_type, row.item_text) for row in items.collect())


def test_lists_become_one_item_per_entry_in_list_order(silver):
    df = silver(
        {
            "unique_id": "a",
            "specialties": '["cardiology","dentistry"]',
            "procedure": '["Angioplasty"]',
            "equipment": '["MRI scanner"]',
            "capability": '["24/7 emergency care"]',
        }
    )
    first_specialty = df.first()["specialties"][0]  # Silver's own spelling of the first item

    items = items_of(df)

    assert ("a:specialty:0", "specialty", first_specialty) in items
    assert [i[1] for i in items].count("specialty") == 2
    assert ("a:procedure:0", "procedure", "Angioplasty") in items
    assert ("a:equipment:0", "equipment", "MRI scanner") in items
    assert ("a:capability:0", "capability", "24/7 emergency care") in items


def test_description_splits_into_sentences_except_after_abbreviations(silver):
    df = silver(
        {
            "unique_id": "a",
            "description": "Dr. Rao runs City Hospital Pvt. Ltd. in Pune. Open 24/7!  Need help? Call now",
        }
    )

    sentences = [text for item_id, kind, text in items_of(df) if kind == "description_sentence"]

    assert sentences == [
        "Dr. Rao runs City Hospital Pvt. Ltd. in Pune.",
        "Open 24/7!",
        "Need help?",
        "Call now",  # Silver base already collapses whitespace
    ]


def test_missing_lists_and_description_give_no_items(silver):
    assert items_of(silver({})) == []


@pytest.fixture
def tables(silver):
    df = silver(
        {"unique_id": "a", "specialties": '["cardiology"]', "description": "One. Two."},
        {"unique_id": "b"},
    ).withColumn("flag_pin_unverified", F.col("unique_id") == "b")
    return (df, *build_gold(df))


def test_real_output_passes_the_checks(tables):
    check_gold(*tables)


def test_a_score_that_does_not_replay_fails(tables):
    silver_df, facilities, items = tables
    broken = facilities.withColumn("confidence_score", F.lit(0.5))

    with pytest.raises(ValueError, match=r"don't replay to confidence_score"):
        check_gold(silver_df, broken, items)


def test_a_changed_copied_value_fails(tables):
    silver_df, facilities, items = tables
    broken = facilities.withColumn("name", F.lit("Other"))

    with pytest.raises(ValueError, match=r"name: 2 row\(s\) differ from Silver"):
        check_gold(silver_df, broken, items)


def test_a_lost_item_fails(tables):
    silver_df, facilities, items = tables
    broken = items.where(F.col("item_type") != "specialty")

    with pytest.raises(ValueError, match=r"specialty items: 1 Facilities"):
        check_gold(silver_df, facilities, broken)


def test_wrong_location_uncertain_fails(tables):
    silver_df, facilities, items = tables
    broken = facilities.withColumn("location_uncertain", F.lit(True))

    with pytest.raises(ValueError, match=r"location_uncertain: 2 row\(s\) differ"):
        check_gold(silver_df, broken, items)


def test_score_counts(tables):
    silver_df, facilities, _ = tables
    counts = score_counts(silver_df, facilities)

    assert counts["rules"]["flag_pin_unverified"] == 1
    assert counts["worst_tier"] == {"critical": 1, "major": 0, "minor": 0, "none": 1}
    assert counts["scores"] == {0.55: 1, 0.8: 1}
    assert "flag_pin_unverified" in format_score_counts(counts)


# confidence_citations: the facility text behind each fired rule.
def cited(row):
    return [(c.rule, c.field, c.item_id, c.text) for c in row.confidence_citations]


def test_every_rule_says_what_it_cites():
    from talaria.gold import citations

    groups = [set(citations.CITED_FIELDS), set(citations.EVIDENCE_RULES), citations.NOTHING_TO_CITE]
    assert set().union(*groups) == {rule.name for rule in scoring.RULES}
    assert sum(len(group) for group in groups) == len(scoring.RULES)


def test_no_fired_rule_cites_nothing(silver):
    row = gold_row(silver({"name": "City Hospital", "address_zipOrPostcode": "600001"}))

    assert row.confidence_citations == []


def test_a_value_rule_cites_its_fields(silver):
    row = gold_row(
        silver({"name": "City Hospital", "address_zipOrPostcode": "600001", "address_stateOrRegion": "Kerala"}),
        flag_pin_mismatch=True,
    )

    assert cited(row) == [
        ("flag_pin_mismatch", "address_state", None, "Kerala"),
        ("flag_pin_mismatch", "address_pincode", None, "600001"),
    ]


def test_a_list_value_is_cited_entry_by_entry(silver):
    row = gold_row(
        silver({"source_urls": '["https://a.example.org/x", "https://a.example.org/y"]'}),
        flag_single_source_domain=True,
    )

    assert cited(row) == [
        ("flag_single_source_domain", "source_urls", None, "https://a.example.org/x"),
        ("flag_single_source_domain", "source_urls", None, "https://a.example.org/y"),
    ]


def test_a_stage3_text_rule_cites_the_matched_items_as_claims(silver):
    df = silver({"unique_id": "f", "specialties": '["cardiology"]', "capability": '["Parking", "24x7 dialysis unit"]'})
    facilities, items = build_gold(df.withColumn("flag_major_orphan", F.lit(True)))

    row = facilities.first()
    assert cited(row) == [("flag_major_orphan", "capability", "f:capability:1", "24x7 dialysis unit")]
    claim = items.where(F.col("item_id") == "f:capability:1").first()
    assert claim.item_text == "24x7 dialysis unit"


def test_stage3_evidence_of_an_unscored_flag_is_not_cited(silver):
    # Stage 3 found evidence, but the fixture keeps the flag false, so nothing fired.
    row = gold_row(silver({"specialties": '["cardiology"]', "capability": '["24x7 dialysis unit"]'}))

    assert row.confidence_citations == []


def test_a_citation_of_an_unknown_item_fails(tables):
    silver_df, facilities, items = tables
    unknown = F.array(
        F.struct(
            F.lit("flag_partial").alias("rule"), F.lit("procedure").alias("field"),
            F.lit("a:procedure:9").alias("item_id"), F.lit("Dialysis").alias("text"),
        )
    )
    broken = facilities.withColumn("confidence_citations", unknown)

    with pytest.raises(ValueError, match=r"2 citation\(s\) whose item_id isn't in gold_facility_items"):
        check_gold(silver_df, broken, items)
