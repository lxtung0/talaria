"""UI text templates for the care finder (ticket #29)."""

from talaria.care_finder import present
from talaria.care_finder.settings import DEFAULT


def result(name="City Hospital", band="strong", evidence=0.8, distance=12.0, confidence=0.5, **extra):
    return {
        "name": name,
        "facility_type": "hospital",
        "distance_km": distance,
        "location_approximate": False,
        "service_evidence": evidence,
        "evidence_band": band,
        "confidence_score": confidence,
        "confidence_band": "medium",
        "distance_factor": 0.9,
        "rank": 0.5,
        "official_phone": "+919876543210",
        "address": {"address_line1": "Main Road", "address_city": "Patna", "address_state": "Bihar", "address_pincode": "800001"},
        "evidence": [
            {"item_type": "equipment", "item_text": "4 Hemodialysis machines*", "label": "direct", "reason": "Has machines", "checked": True},
            {"item_type": "specialty", "item_text": "nephrology", "label": "related", "reason": "Kidney field", "checked": False},
        ],
        **extra,
    }


def answer(top, radius=45.0, stop="enough matches"):
    return {
        "service": "dialysis",
        "urgency": "planned",
        "location": {"label": "Patna, Bihar"},
        "top": top,
        "search": {"searched_radius_km": radius, "rounds": 3, "stop_reason": stop},
        "settings": DEFAULT.as_dict(),
    }


def test_why_lines_quote_the_item_text_verbatim():
    lines = present.why_lines(result())

    assert [line["quote"] for line in lines] == ["4 Hemodialysis machines*", "nephrology"]
    assert lines[0]["label"] == "Says it offers this"
    assert lines[1]["label"] == "Related mention, not checked"


def test_distance_says_approximate_when_the_location_is_in_doubt():
    assert present.distance_text(result()) == "12.0 km away"
    assert present.distance_text(result(location_approximate=True)) == "12.0 km away (approximate)"


def test_summary_with_no_results_names_the_radius_searched():
    text = present.summary(answer([], radius=230.4, stop="max radius reached"))

    assert text == "No facility with any evidence for dialysis was found within about 230 km of Patna, Bihar."


def test_summary_never_calls_weak_evidence_strong():
    weak = [result("Far Clinic", band="some", distance=80), result("Near Clinic", band="mention only", distance=20)]

    text = present.summary(answer(weak))

    assert text.startswith("No facility with strong evidence for dialysis within about 45 km")
    assert "nearest with any evidence is Near Clinic, 20.0 km away" in text


def test_summary_counts_the_strong_results():
    text = present.summary(answer([result(), result(band="some")]))

    assert text.startswith("1 of these 2 facilities has strong evidence")


def test_other_line_names_the_parts_that_scored_worse():
    last_top = result(evidence=0.8, distance=10)

    assert present.other_line(result("B", band="some", evidence=0.5, distance=30), last_top) == (
        "B, 30.0 km away: ranked lower because of less evidence (some evidence) and farther away (30 km)."
    )
    assert present.other_line(result("C", evidence=0.8, distance=5), last_top) == (
        "C, 5.0 km away: ranked lower because of a lower overall score."
    )


def test_formula_uses_the_urgency_distance_scale():
    a = answer([])
    assert "exp(−distance / 100 km)" in present.formula_text(a)
    a["urgency"] = "emergency"
    assert "exp(−distance / 25 km)" in present.formula_text(a)


def test_call_line_needs_a_phone():
    assert present.call_line(result()) == "Call to confirm: +919876543210"
    assert present.call_line(result(official_phone=None)) is None
