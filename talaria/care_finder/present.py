"""Fixed text templates for the care finder UI (ticket #29). Pure functions.

Every line the user reads comes from here, filled with values from the
`recommend()` answer. The LLM writes nothing on a card except the short reason
next to each verbatim quote.
"""

EVIDENCE_WORDS = {
    "strong": "Strong evidence",
    "some": "Some evidence",
    "mention only": "Only a passing mention",
    "none": "No evidence",
}
CONFIDENCE_WORDS = {"high": "High record confidence", "medium": "Medium record confidence", "low": "Low record confidence"}
LABEL_WORDS = {"direct": "Says it offers this", "related": "Related mention"}
TYPE_WORDS = {
    "equipment": "Equipment",
    "procedure": "Procedure",
    "capability": "Capability",
    "description_sentence": "Description",
    "specialty": "Specialty",
}
WHY_LINES = 3
NOT_CHECKED = (
    "Evidence not checked: the automatic check was unavailable, so these matches are based on "
    "text similarity only. Call to confirm before travelling."
)


def distance_text(result: dict) -> str:
    text = f"{result['distance_km']:.1f} km away"
    return f"{text} (approximate)" if result.get("location_approximate") else text


def heading(result: dict, position: int) -> str:
    return f"{position}. {result['name'] or 'Unnamed facility'}"


def subheading(result: dict) -> str:
    kind = (result.get("facility_type") or "facility").replace("_", " ").capitalize()
    return f"{kind} · {distance_text(result)}"


def evidence_line(result: dict, service: str) -> str:
    return f"{EVIDENCE_WORDS[result['evidence_band']]} for {service}"


def confidence_line(result: dict) -> str:
    return CONFIDENCE_WORDS[result["confidence_band"]]


def why_lines(result: dict) -> list[dict]:
    """Up to three quotes, strongest first: the type, the verbatim text, and what the check said."""
    lines = []
    for e in result["evidence"][:WHY_LINES]:
        label = LABEL_WORDS.get(e["label"], e["label"])
        if not e.get("checked", True):
            label = f"{label}, not checked"
        lines.append({"type": TYPE_WORDS.get(e["item_type"], e["item_type"]), "quote": e["item_text"], "label": label, "reason": e.get("reason") or ""})
    return lines


def call_line(result: dict) -> str | None:
    phone = result.get("official_phone")
    return f"Call to confirm: {phone}" if phone else None


def address_line(result: dict) -> str:
    parts = [result["address"].get(c) for c in ("address_line1", "address_city", "address_state", "address_pincode")]
    return ", ".join(p for p in parts if p)


def summary(answer: dict) -> str:
    """One sentence on what was found, which never presents weak evidence as strong."""
    service, place = answer["service"], answer["location"]["label"]
    radius = answer["search"]["searched_radius_km"]
    top = answer["top"]
    if not top:
        return f"No facility with any evidence for {service} was found within about {radius:.0f} km of {place}."
    strong = [r for r in top if r["evidence_band"] == "strong"]
    if not strong:
        nearest = min(top, key=lambda r: r["distance_km"])
        return (
            f"No facility with strong evidence for {service} within about {radius:.0f} km of {place}. "
            f"The nearest with any evidence is {nearest['name']}, {distance_text(nearest)}."
        )
    verb = "has" if len(strong) == 1 else "have"
    return f"{len(strong)} of these {len(top)} facilities {verb} strong evidence for {service}, searched up to about {radius:.0f} km from {place}."


def search_extent(answer: dict) -> str:
    s = answer["search"]
    why = "enough strong matches were found" if s["stop_reason"] == "enough matches" else "it reached the maximum distance"
    steps = "1 step" if s["rounds"] == 1 else f"{s['rounds']} steps"
    return f"Searched about {s['searched_radius_km']:.0f} km around {answer['location']['label']} in {steps}; stopped because {why}."


def other_line(result: dict, last_top: dict | None) -> str:
    """Why an option ranked below the shown three, from the score parts that are worse."""
    because = []
    if last_top:
        if result["service_evidence"] < last_top["service_evidence"]:
            because.append(f"less evidence ({EVIDENCE_WORDS[result['evidence_band']].lower()})")
        if result["distance_km"] > last_top["distance_km"]:
            because.append(f"farther away ({result['distance_km']:.0f} km)")
        if result["confidence_score"] < last_top["confidence_score"]:
            because.append("lower record confidence")
    reason = " and ".join(because) or "a lower overall score"
    return f"{result['name']}, {distance_text(result)}: ranked lower because of {reason}."


def formula_text(answer: dict) -> str:
    s = answer["settings"]
    d0 = s["distance_decay_km"][answer["urgency"]]
    tiers = ", ".join(f"{tier} {value:g}" for tier, value in s["affordability_values"].items())
    return (
        "hit value = label value × type weight; only the best "
        f"{s['hits_per_type']} hits of each type count\n"
        "service evidence = 1 − Π(1 − hit value)\n"
        f"rank = service evidence × (0.5 + 0.5 × confidence) × exp(−distance / {d0:.0f} km) × affordability\n"
        f"affordability = 1 + {s['affordability_max_boost']} × tier × share of households uninsured here "
        f"({tiers}, other 0)"
    )


def score_parts(result: dict) -> list[dict]:
    return [
        {"part": "Service evidence", "value": result["service_evidence"], "band": result["evidence_band"]},
        {"part": "Record confidence", "value": result["confidence_score"], "band": result["confidence_band"]},
        {"part": "Distance factor", "value": result["distance_factor"], "band": f"{result['distance_km']:.1f} km"},
        {"part": "Affordability factor", "value": result["affordability_factor"], "band": result["affordability"] or "—"},
        {"part": "Rank", "value": result["rank"], "band": ""},
    ]
