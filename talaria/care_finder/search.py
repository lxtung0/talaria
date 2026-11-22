"""The expanding H3 search loop (#28 steps 2–4).

`expanding_search` grows a ring of H3 cells around the start point one band at
a time. It takes the IO as two functions, so the loop is tested with fakes:

- `search_band(cells) -> hits`: Vector Search over the claims in those cells;
  each hit has `item_id`, `unique_id`, `item_type`, `item_text`, `h3_r5`, `similarity`.
- `label_hits(hits) -> (labels, info)`: `{item_id: {label, reason}}` for the hits,
  plus `{cache_hits, llm_calls, fallback_used}`.
"""

import math
from typing import Callable

import h3

from talaria.care_finder import tracing
from talaria.care_finder.settings import DEFAULT, Settings

ENOUGH, MAX_RADIUS = "enough matches", "max radius reached"


def k_steps(settings: Settings = DEFAULT) -> list[int]:
    """1, 2, …, small_k_limit, then every large_k_step, ending exactly at max_k."""
    steps, k = [], 1
    while k < settings.max_k:
        steps.append(k)
        k += 1 if k < settings.small_k_limit else settings.large_k_step
    return steps + [settings.max_k]


def radius_km(k: int, settings: Settings = DEFAULT) -> float:
    """Approximate distance from the start cell's centre to the edge of ring k."""
    edge = h3.average_hexagon_edge_length(settings.h3_resolution, unit="km")
    return round(edge * (math.sqrt(3) * k + 1), 1)


def expanding_search(
    lat: float,
    lon: float,
    search_band: Callable[[list[str]], list[dict]],
    label_hits: Callable[[list[dict]], tuple[dict, dict]],
    settings: Settings = DEFAULT,
) -> dict:
    """Labelled hits from every round, plus the search extent and per-round details."""
    start = h3.latlng_to_cell(lat, lon, settings.h3_resolution)
    searched: set[str] = set()
    hits: dict[str, dict] = {}
    rounds = []
    stop = MAX_RADIUS
    for k in k_steps(settings):
        band = sorted(set(h3.grid_disk(start, k)) - searched)
        searched.update(band)
        with tracing.span(f"round {len(rounds) + 1}", {"k": k, "new_cells": len(band)}) as span:
            found = [h for h in search_band(band) if h["item_id"] not in hits]
            kept = [h for h in found if h["similarity"] >= settings.min_similarity]
            labels, info = label_hits(kept) if kept else ({}, {"cache_hits": 0, "llm_calls": 0, "fallback_used": False})
            for hit in kept:
                if hit["item_id"] in labels:
                    hits[hit["item_id"]] = {**hit, **labels[hit["item_id"]], "round": len(rounds) + 1}
            direct = direct_facilities(hits.values())
            span.set_outputs(
                {
                    "hits_found": len(found),
                    "hits_kept": len(kept),
                    "new_facilities": len({h["unique_id"] for h in kept}),
                    "direct_facilities_so_far": len(direct),
                }
            )
        rounds.append(
            {
                "k": k,
                "radius_km": radius_km(k, settings),
                "cells": band,
                "hits_found": len(found),
                "hits_kept": len(kept),
                "facilities_checked": sorted({h["unique_id"] for h in kept}),
                "direct_facilities": len(direct),
                **info,
            }
        )
        if len(direct) >= settings.min_direct_facilities:
            stop = ENOUGH
            break
    return {
        "start_cell": start,
        "hits": list(hits.values()),
        "rounds": rounds,
        "searched_k": rounds[-1]["k"],
        "searched_radius_km": rounds[-1]["radius_km"],
        "stop_reason": stop,
        "fallback_used": any(r["fallback_used"] for r in rounds),
    }


def direct_facilities(hits) -> set[str]:
    return {h["unique_id"] for h in hits if h.get("label") == "direct"}
