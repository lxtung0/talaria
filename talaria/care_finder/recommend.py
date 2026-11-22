"""`recommend(service, location, urgency)`: the whole care finder query flow (ticket #28).

All IO goes through a backend (see `backend.DatabricksBackend`); everything
here is plain Python, so the flow is tested with a fake backend.
"""

from talaria.care_finder import labels as labels_mod
from talaria.care_finder import reasons, scoring
from talaria.care_finder.location import LocationError, Place, choose_location, parse_location
from talaria.care_finder.search import best_labels, direct_facilities, expanding_search
from talaria.care_finder.settings import DEFAULT, Settings

URGENCIES = ("emergency", "planned")
ADDRESS_COLUMNS = ["address_line1", "address_line2", "address_line3", "address_city", "address_state", "address_pincode"]


def recommend(
    service: str, location: str, urgency: str = "planned", *, backend=None, settings: Settings = DEFAULT, on_progress=None
) -> dict:
    """The best Facilities for `service` near `location`, with their evidence.

    `status` is `ok` (results, possibly empty), `ambiguous` (`candidates` to choose
    from, each usable as a new `location`) or `error` (`error` is shown to the user).
    `on_progress(event)` is called as the search runs: `located`, then each round's
    `band`, `found` and `checked` (see `search.expanding_search`), for the live map.
    """
    if backend is None:
        from talaria.care_finder.backend import DatabricksBackend

        backend = DatabricksBackend()
    service = (service or "").strip()
    urgency = urgency if urgency in URGENCIES else "planned"
    base = {"service": service, "location_query": location, "urgency": urgency, "settings": settings.as_dict()}
    if not service:
        return {**base, "status": "error", "error": "Enter a service, such as dialysis or MRI."}

    try:
        place = resolve_location(location, backend)
    except LocationError as e:
        return {**base, "status": "error", "error": str(e)}
    if isinstance(place, list):
        return {**base, "status": "ambiguous", "candidates": [p.label for p in place]}

    if on_progress is not None:
        try:
            on_progress({"type": "located", "label": place.label, "lat": place.lat, "lon": place.lon})
        except Exception:
            pass  # drawing the search must never break it

    service_key = labels_mod.normalize_service(service)
    cache = backend.cached_labels(service_key)
    new_labels: dict[str, dict] = {}

    def search_band(cells):
        return backend.search_band(service, cells, settings.results_per_round)

    def label_hits(hits):
        return _label_hits(service, hits, cache, new_labels, backend, settings)

    found = expanding_search(place.lat, place.lon, search_band, label_hits, settings, on_progress)
    if new_labels:
        backend.save_labels(service_key, new_labels)

    # One read for every Facility checked: the scored ones and, for the search map, the rest.
    checked = sorted({uid for r in found["rounds"] for uid in r["facilities_checked"]})
    facilities = {f["unique_id"]: f for f in backend.facilities(checked)} if checked else {}
    results = score_facilities(found["hits"], facilities, place, urgency, settings)
    return {
        **base,
        "status": "ok",
        "location": {"label": place.label, "kind": place.kind, "lat": place.lat, "lon": place.lon},
        "top": results[: settings.top_n],
        "others": results[settings.top_n : settings.top_n + settings.others_n],
        "evidence_checked": not found["fallback_used"],
        "search": {
            "searched_k": found["searched_k"],
            "searched_radius_km": found["searched_radius_km"],
            "rounds": len(found["rounds"]),
            "stop_reason": found["stop_reason"],
            "direct_facilities": len(direct_facilities(found["hits"])),
        },
        "rounds": map_rounds(found["rounds"], found["hits"], facilities),
        "round_details": [{k: v for k, v in r.items() if k not in ("cells", "candidates", "facilities_checked")} for r in found["rounds"]],
    }


def map_rounds(rounds: list[dict], hits: list[dict], facilities: dict) -> list[dict]:
    """Per round, for the search map: `k`, the new H3 cells, and every Facility found in it
    with its best label (None when it was ruled out)."""
    best = best_labels(hits)
    return [
        {
            "k": r["k"],
            "radius_km": r["radius_km"],
            "cells": r["cells"],
            "facilities": [
                {
                    "unique_id": c["unique_id"],
                    "lat": facilities[c["unique_id"]]["latitude"] if c["unique_id"] in facilities else c["lat"],
                    "lon": facilities[c["unique_id"]]["longitude"] if c["unique_id"] in facilities else c["lon"],
                    "label": best.get(c["unique_id"]),
                }
                for c in r["candidates"]
            ],
        }
        for r in rounds
    ]


def resolve_location(text: str, backend) -> Place | list[Place]:
    parsed = parse_location(text)
    if parsed[0] == "coords":
        return Place(f"{parsed[1]:.4f}, {parsed[2]:.4f}", "coordinates", parsed[1], parsed[2])
    if parsed[0] == "pin":
        place = backend.pin_place(parsed[1])
        if place is None:
            raise LocationError(f"PIN {parsed[1]} wasn't found in the India Post directory.")
        return place
    _, name, state = parsed
    return choose_location(text, backend.district_places(name, state), backend.city_places(name, state))


def _label_hits(service, hits, cache, new_labels, backend, settings):
    """Cached labels first; one LLM call for the rest; the similarity fallback if it fails.

    Only the selected hits (top hits of the top Facilities) are labelled, cached or not,
    so the same query labels the same hits every time and a repeat needs no LLM call.
    """
    selected = labels_mod.select_for_llm(hits, settings)
    labels = {h["item_id"]: cache[h["item_id"]] for h in selected if h["item_id"] in cache}
    to_check = [h for h in selected if h["item_id"] not in cache]
    info = {"cache_hits": len(labels), "llm_calls": 0, "fallback_used": False}
    if to_check:
        info["llm_calls"] = 1
        try:
            reply = backend.chat(labels_mod.build_prompt(service, to_check))
            checked = labels_mod.validate_labels(labels_mod.parse_llm_output(reply), [h["item_id"] for h in to_check])
            new_labels.update(checked)
            cache.update(checked)
            labels.update({k: {**v, "checked": True} for k, v in checked.items()})
        except Exception as e:  # any failure of the call or its reply: label by similarity instead
            info["fallback_used"] = True
            info["llm_error"] = f"{type(e).__name__}: {e}"[:300]
            fallback = labels_mod.similarity_fallback(to_check, settings)
            labels.update({k: {**v, "checked": False} for k, v in fallback.items()})
    for item_id, label in labels.items():
        label.setdefault("checked", True)
    return labels, info


def score_facilities(hits: list[dict], facilities: dict, place: Place, urgency: str, settings: Settings = DEFAULT) -> list[dict]:
    """One result per Facility with a direct or related hit, best rank first. `facilities` is by `unique_id`."""
    by_facility: dict[str, list[dict]] = {}
    for hit in hits:
        if hit["label"] in ("direct", "related"):
            by_facility.setdefault(hit["unique_id"], []).append(hit)
    results = [
        build_result(facilities[uid], facility_hits, place, urgency, settings)
        for uid, facility_hits in by_facility.items()
        if uid in facilities
    ]
    return sorted(results, key=lambda r: (-r["rank"], r["distance_km"]))


def build_result(facility: dict, hits: list[dict], place: Place, urgency: str, settings: Settings = DEFAULT) -> dict:
    distance = scoring.haversine_km(place.lat, place.lon, facility["latitude"], facility["longitude"])
    evidence = scoring.service_evidence(hits, settings)
    confidence = facility.get("confidence_score")
    confidence = 0.5 if confidence is None else float(confidence)
    counted = {h["item_id"] for h in scoring.counted_hits(hits, settings)}
    ordered = sorted(hits, key=lambda h: (-scoring.hit_value(h["label"], h["item_type"], settings), -h["similarity"]))
    return {
        "unique_id": facility["unique_id"],
        "name": facility.get("name"),
        "facility_type": facility.get("facility_type"),
        "address": {c: facility.get(c) for c in ADDRESS_COLUMNS},
        "latitude": facility["latitude"],
        "longitude": facility["longitude"],
        "official_phone": facility.get("official_phone"),
        "official_website": facility.get("official_website"),
        "source_urls": facility.get("source_urls") or [],
        "distance_km": round(distance, 1),
        "location_approximate": reasons.location_approximate(facility),
        "service_evidence": round(evidence, 3),
        "evidence_band": scoring.evidence_band(evidence, settings),
        "confidence_score": confidence,
        "confidence_band": scoring.confidence_band(confidence, settings),
        "confidence_reasons": facility.get("confidence_reasons") or [],
        "distance_factor": round(scoring.distance_decay(distance, urgency, settings), 3),
        "rank": round(scoring.rank_score(evidence, confidence, distance, urgency, settings), 4),
        "evidence": [
            {
                "item_id": h["item_id"],
                "item_type": h["item_type"],
                "item_text": h["item_text"],
                "similarity": round(h["similarity"], 3),
                "label": h["label"],
                "reason": h.get("reason", ""),
                "checked": h.get("checked", True),
                "value": round(scoring.hit_value(h["label"], h["item_type"], settings), 3),
                "counted": h["item_id"] in counted,
            }
            for h in ordered
        ],
        "warnings": reasons.warnings(facility),
        "good_points": reasons.good_points(facility),
    }
