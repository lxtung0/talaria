"""The expanding H3 search loop (#28 steps 2–4).

`expanding_search` grows a ring of H3 cells around the start point one band at
a time. It takes the IO as two functions, so the loop is tested with fakes:

- `search_band(cells) -> hits`: Vector Search over the claims in those cells;
  each hit has `item_id`, `unique_id`, `item_type`, `item_text`, `h3_r5`, `similarity`.
- `label_hits(hits) -> (labels, info)`: `{item_id: {label, reason}}` for the hits,
  plus `{cache_hits, llm_calls, fallback_used}`.

`on_event`, if given, is called as the search runs, so the app can draw it live:
`band` (a round starts: its cells), `found` (the Facilities with a similar claim)
and `checked` (each found Facility's best label, or None when ruled out).
"""

import math
from typing import Callable

import h3

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
    on_event: Callable[[dict], None] | None = None,
) -> dict:
    """Labelled hits from every round, plus the search extent and per-round details."""
    emit = _safe(on_event)
    start = h3.latlng_to_cell(lat, lon, settings.h3_resolution)
    searched: set[str] = set()
    hits: dict[str, dict] = {}
    rounds = []
    stop = MAX_RADIUS
    for k in k_steps(settings):
        band = sorted(set(h3.grid_disk(start, k)) - searched)
        searched.update(band)
        n = len(rounds) + 1
        emit({"type": "band", "round": n, "k": k, "radius_km": radius_km(k, settings), "cells": band})
        found = [h for h in search_band(band) if h["item_id"] not in hits]
        candidates = _candidates(found)
        emit({"type": "found", "round": n, "candidates": candidates, "hits": len(found)})
        kept = [h for h in found if h["similarity"] >= settings.min_similarity]
        labels, info = label_hits(kept) if kept else ({}, {"cache_hits": 0, "llm_calls": 0, "fallback_used": False})
        for hit in kept:
            if hit["item_id"] in labels:
                hits[hit["item_id"]] = {**hit, **labels[hit["item_id"]], "round": n}
        direct = direct_facilities(hits.values())
        best = best_labels(h for h in hits.values() if h["round"] == n)
        emit({"type": "checked", "round": n, "labels": {c["unique_id"]: best.get(c["unique_id"]) for c in candidates}, "direct_so_far": len(direct)})
        rounds.append(
            {
                "k": k,
                "radius_km": radius_km(k, settings),
                "cells": band,
                "candidates": candidates,
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


def best_labels(hits) -> dict[str, str]:
    """Each Facility's best label among its hits: direct over related; unrelated is left out."""
    best: dict[str, str] = {}
    for hit in hits:
        if hit.get("label") == "direct" or (hit.get("label") == "related" and best.get(hit["unique_id"]) != "direct"):
            best[hit["unique_id"]] = hit["label"]
    return best


def _candidates(found: list[dict]) -> list[dict]:
    """One point per Facility with a hit: its coordinates, or its cell's centre when the search didn't return them."""
    points = {}
    for hit in found:
        if hit["unique_id"] in points:
            continue
        lat, lon = hit.get("latitude"), hit.get("longitude")
        if lat is None or lon is None:
            lat, lon = h3.cell_to_latlng(hit["h3_r5"])
        points[hit["unique_id"]] = {"unique_id": hit["unique_id"], "lat": lat, "lon": lon}
    return list(points.values())


def _safe(callback):
    """The callback, with its errors swallowed: drawing the search must never break it."""

    def call(event: dict) -> None:
        if callback is None:
            return
        try:
            callback(event)
        except Exception:
            pass

    return call
