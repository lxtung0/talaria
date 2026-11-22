"""The healthcare desert check (#46): did the search need too many rings to find the service?

Rings needed is the H3 grid distance from the start cell to the nearest Facility
with a `direct` hit. More than `settings.desert_k[urgency]`, or no `direct` hit
out to `max_k`, is a possible desert. Pure: it only reads what the search found.
"""

import h3

from talaria.care_finder.search import radius_km
from talaria.care_finder.settings import DEFAULT, Settings


def desert_check(found: dict, results: list[dict], urgency: str, settings: Settings = DEFAULT) -> dict:
    """`found` is `expanding_search`'s output; `results` are every scored Facility, not just the top."""
    threshold_k = settings.desert_k[urgency]
    start = found["start_cell"]
    rings = [h3.grid_distance(start, h["h3_r5"]) for h in found["hits"] if h.get("label") == "direct"]
    rings_needed = min(rings) if rings else None
    direct_km = [r["distance_km"] for r in results if any(e["label"] == "direct" for e in r["evidence"])]
    return {
        "is_desert": rings_needed is None or rings_needed > threshold_k,
        "threshold_k": threshold_k,
        "threshold_km": radius_km(threshold_k, settings),
        "rings_needed": rings_needed,
        "nearest_direct_km": min(direct_km) if direct_km else None,
        "start_cell": start,
    }
