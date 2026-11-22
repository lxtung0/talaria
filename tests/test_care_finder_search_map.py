"""The live search map's state and captions (ticket #33), from progress events."""

from talaria.care_finder.search_map import SearchView, replay_events, view_after_round


def _events():
    return [
        {"type": "located", "label": "Patna, Bihar", "lat": 25.6, "lon": 85.1},
        {"type": "band", "round": 1, "k": 1, "radius_km": 26.9, "cells": ["a", "b"]},
        {"type": "found", "round": 1, "candidates": [{"unique_id": u, "lat": 25.6, "lon": 85.1} for u in ("x", "y", "z")]},
        {"type": "checked", "round": 1, "labels": {"x": "direct", "y": "related", "z": None}, "direct_so_far": 1},
    ]


def test_captions_follow_each_step_of_a_round():
    view, captions = SearchView(), []
    for event in _events():
        view.apply(event)
        captions.append(view.caption())

    assert captions == [
        "Starting the search around Patna, Bihar…",
        "Round 1 · searching 2 new map cells, out to about 27 km…",
        "Round 1 · 3 facilities mention something similar · checking the evidence…",
        "Round 1 · 1 confirmed, 1 related, 1 ruled out · 1 confirmed so far",
    ]


def test_found_facilities_are_grey_until_checked_then_coloured_or_faded():
    view = SearchView()
    for event in _events()[:3]:
        view.apply(event)
    assert all(not p["checked"] for p in view.rounds[0]["points"].values())

    view.apply(_events()[3])
    points = view.rounds[0]["points"]
    assert (points["x"]["label"], points["y"]["label"], points["z"]["label"]) == ("direct", "related", None)
    assert all(p["checked"] for p in points.values())
    view.deck()  # draws without error


def test_replay_rebuilds_the_live_events_and_ends_on_the_named_top_results():
    answer = {
        "location": {"label": "Patna, Bihar", "lat": 25.6, "lon": 85.1},
        "rounds": [
            {"k": 1, "radius_km": 26.9, "cells": ["a"], "facilities": [{"unique_id": "x", "lat": 25.6, "lon": 85.1, "label": None}]},
            {"k": 2, "radius_km": 42.0, "cells": ["b"], "facilities": [{"unique_id": "y", "lat": 25.7, "lon": 85.2, "label": "direct"}]},
        ],
        "top": [{"name": "Y Hospital", "latitude": 25.7, "longitude": 85.2}],
    }

    assert [e["type"] for e in replay_events(answer)] == ["located", "band", "found", "checked", "band", "found", "checked"]
    assert view_after_round(answer, 0).caption() == "Round 1 · 0 confirmed, 0 related, 1 ruled out · 0 confirmed so far"
    assert view_after_round(answer, 1).caption() == "Done after 2 rounds, about 42 km · 1. Y Hospital"
