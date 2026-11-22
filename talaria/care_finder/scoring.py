"""Score and band Facilities from their labelled hits (spec #28, step 5). Pure functions."""

import math
from collections import defaultdict

from talaria.care_finder.settings import DEFAULT, Settings

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def hit_value(label: str, item_type: str, settings: Settings = DEFAULT) -> float:
    """label value × type weight; 0 for `unrelated` or an unknown type."""
    return settings.label_values.get(label, 0.0) * settings.type_weights.get(item_type, 0.0)


def counted_hits(hits: list[dict], settings: Settings = DEFAULT) -> list[dict]:
    """The hits that count: the best `hits_per_type` of each `item_type` with a value above 0."""
    by_type = defaultdict(list)
    for hit in hits:
        value = hit_value(hit["label"], hit["item_type"], settings)
        if value > 0:
            by_type[hit["item_type"]].append({**hit, "value": value})
    counted = []
    for typed in by_type.values():
        typed.sort(key=lambda h: (-h["value"], -h.get("similarity", 0.0)))
        counted.extend(typed[: settings.hits_per_type])
    return sorted(counted, key=lambda h: (-h["value"], -h.get("similarity", 0.0)))


def noisy_or(values: list[float]) -> float:
    product = 1.0
    for value in values:
        product *= 1.0 - value
    return 1.0 - product


def service_evidence(hits: list[dict], settings: Settings = DEFAULT) -> float:
    return noisy_or([h["value"] for h in counted_hits(hits, settings)])


def distance_decay(distance_km: float, urgency: str, settings: Settings = DEFAULT) -> float:
    d0 = settings.distance_decay_km.get(urgency, settings.distance_decay_km["planned"])
    return math.exp(-distance_km / d0)


def open_24_7_factor(open_24_7: bool, urgency: str, settings: Settings = DEFAULT) -> float:
    """1 for planned care; for an emergency, 1 if the Facility says it is open 24/7, else 1 − weight."""
    if urgency != "emergency":
        return 1.0
    w = settings.emergency_24_7_weight
    return 1.0 - w + w * open_24_7


def rank_score(
    evidence: float, confidence: float, distance_km: float, urgency: str, settings: Settings = DEFAULT, open_24_7: bool = False
) -> float:
    return (
        evidence
        * (0.5 + 0.5 * confidence)
        * distance_decay(distance_km, urgency, settings)
        * open_24_7_factor(open_24_7, urgency, settings)
    )


def evidence_band(evidence: float, settings: Settings = DEFAULT) -> str:
    for band, threshold in settings.evidence_bands:
        if evidence >= threshold:
            return band
    return "mention only" if evidence > 0 else "none"


def confidence_band(confidence: float, settings: Settings = DEFAULT) -> str:
    (high, high_above), (medium, medium_from) = settings.confidence_bands
    if confidence > high_above:
        return high
    return medium if confidence >= medium_from else "low"
