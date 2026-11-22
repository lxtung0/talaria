"""Scoring, bands, reasons and label checks for the care finder (ticket #28). Pure Python, no Spark."""

import math

import pytest

from talaria.care_finder import labels, reasons, scoring
from talaria.care_finder.location import LocationError, Place, choose_location, parse_location


def hit(item_type, label="direct", similarity=0.9, item_id=None):
    return {"item_id": item_id or f"{item_type}-{label}-{similarity}", "item_type": item_type, "label": label, "similarity": similarity}


# --- hit values, cap, noisy-OR, rank ------------------------------------


@pytest.mark.parametrize(
    "label, item_type, expected",
    [
        ("direct", "equipment", 0.7),
        ("related", "equipment", 0.28),
        ("direct", "procedure", 0.7),
        ("direct", "capability", 0.6),
        ("direct", "description_sentence", 0.5),
        ("related", "specialty", 0.1),
        ("unrelated", "equipment", 0.0),
    ],
)
def test_hit_value_is_label_value_times_type_weight(label, item_type, expected):
    assert scoring.hit_value(label, item_type) == pytest.approx(expected)


def test_only_the_best_two_hits_of_each_type_count():
    hits = [hit("equipment", similarity=s) for s in (0.95, 0.91, 0.85)] + [hit("equipment", "related", 0.99)]

    counted = scoring.counted_hits(hits)

    assert [h["similarity"] for h in counted] == [0.95, 0.91]


def test_service_evidence_is_noisy_or_of_the_counted_hits():
    hits = [hit("equipment", similarity=0.95), hit("equipment", similarity=0.92), hit("equipment", similarity=0.9), hit("specialty")]

    # Two equipment hits (0.7 each) and one specialty hit (0.25); the third equipment hit is capped.
    assert scoring.service_evidence(hits) == pytest.approx(1 - 0.3 * 0.3 * 0.75)


def test_noisy_or_of_nothing_is_zero():
    assert scoring.noisy_or([]) == 0.0


def test_rank_is_evidence_times_confidence_factor_times_distance_decay():
    assert scoring.rank_score(0.8, 0.5, 50, "planned") == pytest.approx(0.8 * 0.75 * math.exp(-50 / 100))
    assert scoring.rank_score(0.8, 0.5, 50, "emergency") == pytest.approx(0.8 * 0.75 * math.exp(-50 / 25) * 0.85)


def test_an_emergency_rank_has_a_24_7_factor_and_a_planned_one_does_not():
    assert scoring.rank_score(0.8, 0.5, 50, "emergency", open_24_7=True) == pytest.approx(0.8 * 0.75 * math.exp(-50 / 25))
    assert scoring.rank_score(0.8, 0.5, 50, "planned", open_24_7=True) == scoring.rank_score(0.8, 0.5, 50, "planned")


def test_haversine_patna_to_lucknow_is_about_470_km():
    assert scoring.haversine_km(25.5941, 85.1376, 26.8467, 80.9462) == pytest.approx(440, abs=40)


@pytest.mark.parametrize(
    "evidence, band", [(0.75, "strong"), (0.9, "strong"), (0.5, "some"), (0.74, "some"), (0.1, "mention only"), (0.0, "none")]
)
def test_evidence_bands(evidence, band):
    assert scoring.evidence_band(evidence) == band


@pytest.mark.parametrize("confidence, band", [(0.71, "high"), (0.7, "medium"), (0.5, "medium"), (0.49, "low")])
def test_confidence_bands(confidence, band):
    assert scoring.confidence_band(confidence) == band


# --- reasons --------------------------------------------------------------


def test_a_true_problem_flag_gives_its_warning():
    facility = {"flag_only_directory_sources": True, "flag_single_source_domain": False}

    assert reasons.warnings(facility) == ["Only found on directory or social media sites"]


def test_a_true_location_flag_warns_location_may_be_inaccurate_and_makes_distance_approximate():
    facility = {"flag_coords_shared": True}

    assert reasons.warnings(facility)[0].startswith("Location may be inaccurate")
    assert reasons.location_approximate(facility)
    assert not reasons.location_approximate({"flag_coords_shared": False})


def test_a_truncated_list_warns_the_list_is_incomplete():
    facility = {"needs_investigation": True, "truncated_columns": ["procedure"]}

    assert reasons.warnings(facility) == [
        "List incomplete (procedures cut off at 50 items), so a missing service may just be unlisted"
    ]


def test_a_good_point_only_comes_from_a_true_positive_flag():
    assert reasons.good_points({"flag_has_government_source": True, "flag_own_site_in_sources": False}) == [
        "Listed on a government website"
    ]


def test_false_flags_give_no_good_points_and_no_warnings():
    every_flag = {f: False for f in [*reasons.GOOD_FLAGS, *reasons.LOCATION_FLAGS, *reasons.WARNING_FLAGS]}

    assert reasons.good_points(every_flag) == []
    assert reasons.warnings(every_flag) == []


# --- label validation and fallback -----------------------------------------


def test_validation_drops_unknown_ids_and_labels_and_marks_missing_items_unrelated():
    raw = [
        {"item_id": "a", "label": "direct", "reason": "Has dialysis machines"},
        {"item_id": "b", "label": "maybe", "reason": "?"},
        {"item_id": "zzz", "label": "direct", "reason": "not sent"},
        "garbage",
    ]

    validated = labels.validate_labels(raw, ["a", "b", "c"])

    assert set(validated) == {"a", "b", "c"}
    assert validated["a"] == {"label": "direct", "reason": "Has dialysis machines"}
    assert validated["b"]["label"] == "unrelated"
    assert validated["c"]["label"] == "unrelated"


def test_parse_llm_output_reads_json_inside_a_code_fence():
    assert labels.parse_llm_output('```json\n{"labels": [{"item_id": "a"}]}\n```') == [{"item_id": "a"}]


def test_parse_llm_output_rejects_a_reply_without_labels():
    with pytest.raises(ValueError):
        labels.parse_llm_output("Sorry, I can't help with that.")


def test_similarity_fallback_labels_direct_from_090_and_related_from_min_similarity():
    hits = [hit("equipment", similarity=s, item_id=str(s)) for s in (0.95, 0.9, 0.85, 0.7, 0.69)]

    fallback = labels.similarity_fallback(hits)

    assert [fallback[str(s)]["label"] for s in (0.95, 0.9, 0.85, 0.7, 0.69)] == [
        "direct", "direct", "related", "related", "unrelated"
    ]
    assert all("Evidence not checked" in v["reason"] for v in fallback.values())


def test_select_for_llm_sends_top_five_hits_for_top_fifteen_facilities():
    hits = [
        {"item_id": f"f{f}-{i}", "unique_id": f"f{f}", "similarity": 0.99 - f * 0.01 - i * 0.0001}
        for f in range(20)
        for i in range(7)
    ]

    chosen = labels.select_for_llm(hits)

    assert len({h["unique_id"] for h in chosen}) == 15
    assert len(chosen) == 75
    assert {h["unique_id"] for h in chosen} == {f"f{f}" for f in range(15)}


# --- location ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text, parsed",
    [
        ("800001", ("pin", "800001")),
        ("800 001", ("pin", "800001")),
        ("25.59,85.14", ("coords", 25.59, 85.14)),
        (" 25.59, 85.14 ", ("coords", 25.59, 85.14)),
        ("Patna", ("name", "Patna", None)),
        ("Aurangabad, Bihar", ("name", "Aurangabad", "Bihar")),
    ],
)
def test_parse_location(text, parsed):
    assert parse_location(text) == parsed


def test_a_district_name_wins_over_a_city_name():
    district = Place("Patna, Bihar", "district", 25.6, 85.1, "BIHAR")
    city = Place("Patna, Somewhere", "city", 25.61, 85.13, "Somewhere")

    assert choose_location("Patna", [district], [city]) == district


def test_a_city_is_used_when_no_district_matches():
    city = Place("Ghaziabad, Uttar Pradesh", "city", 28.67, 77.45, "Uttar Pradesh")

    assert choose_location("Ghaziabad", [], [city]) == city


def test_a_name_in_two_states_is_ambiguous():
    places = [Place("Aurangabad, Maharashtra", "district", 19.9, 75.3, "MAHARASHTRA"), Place("Aurangabad, Bihar", "district", 24.8, 84.4, "BIHAR")]

    assert choose_location("Aurangabad", places, []) == sorted(places, key=lambda p: p.label)


def test_an_unknown_name_is_a_clear_error():
    with pytest.raises(LocationError, match="Atlantis"):
        choose_location("Atlantis", [], [])


def test_insurance_need_is_zero_unless_coverage_is_below_the_national_figure():
    assert scoring.insurance_need(None) == 0.0
    assert scoring.insurance_need(41.0) == 0.0
    assert scoring.insurance_need(80.0) == 0.0
    assert scoring.insurance_need(20.5) == pytest.approx(0.5)
    assert scoring.insurance_need(0.0) == 1.0


def test_affordability_factor_scales_with_tier_and_need():
    assert scoring.affordability_factor("government", 1.0) == pytest.approx(1.15)
    assert scoring.affordability_factor("public", 0.5) == pytest.approx(1 + 0.15 * 0.33 * 0.5)
    assert scoring.affordability_factor(None, 1.0) == 1.0
    assert scoring.affordability_factor("government", 0.0) == 1.0
