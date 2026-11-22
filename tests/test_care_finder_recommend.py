"""The expanding search loop and `recommend()` with fake IO (ticket #28)."""

import h3
import pytest

from talaria.care_finder.location import Place
from talaria.care_finder.recommend import recommend
from talaria.care_finder.search import ENOUGH, MAX_RADIUS, expanding_search, k_steps
from talaria.care_finder.settings import Settings

PATNA = (25.5941, 85.1376)


def facility_at(lat, lon, unique_id, **flags):
    return {"unique_id": unique_id, "name": f"Hospital {unique_id}", "latitude": lat, "longitude": lon, "confidence_score": 0.5, **flags}


class FakeBackend:
    """Facilities at fixed points, each with one claim; labels come from `llm_labels`."""

    def __init__(self, facilities, texts, llm_labels=None, llm_fails=False, area=None):
        self.area_row = area  # what `area()` returns; an Exception instance is raised
        self.facilities_by_id = {f["unique_id"]: f for f in facilities}
        self.texts = texts  # unique_id -> (item_type, item_text, similarity)
        self.llm_labels = llm_labels or {}
        self.llm_fails = llm_fails
        self.cache: dict[str, dict] = {}
        self.chat_calls = 0
        self.band_calls: list[list[str]] = []

    def pin_place(self, pin):
        return Place(f"PIN {pin}", "pin", *PATNA) if pin == "800001" else None

    def district_places(self, name, state):
        return [Place("Patna, Bihar", "district", *PATNA, "BIHAR")] if name.lower() == "patna" else []

    def city_places(self, name, state):
        return []

    def search_band(self, service, cells, n):
        self.band_calls.append(cells)
        hits = []
        for uid, f in self.facilities_by_id.items():
            cell = h3.latlng_to_cell(f["latitude"], f["longitude"], 5)
            if cell in cells:
                item_type, text, similarity = self.texts[uid]
                hits.append({"item_id": f"{uid}-e0", "unique_id": uid, "item_type": item_type, "item_text": text, "h3_r5": cell, "similarity": similarity})
        return hits[:n]

    def chat(self, messages):
        self.chat_calls += 1
        if self.llm_fails:
            raise TimeoutError("model down")
        import json

        prompt = messages[-1]["content"]
        ids = [line.split("\t")[0] for line in prompt.splitlines() if "\t" in line]
        return json.dumps({"labels": [{"item_id": i, "label": self.llm_labels.get(i, "direct"), "reason": "says so"} for i in ids]})

    def cached_labels(self, key):
        return {k: dict(v) for k, v in self.cache.get(key, {}).items()}

    def save_labels(self, key, labels):
        self.cache.setdefault(key, {}).update(labels)

    def facilities(self, ids):
        return [self.facilities_by_id[i] for i in ids]

    def area(self, lat, lon):
        if isinstance(self.area_row, Exception):
            raise self.area_row
        return self.area_row


def ring_points(k_cells_away, count, start=PATNA):
    """`count` points in distinct cells exactly `k_cells_away` rings from the start cell."""
    start_cell = h3.latlng_to_cell(*start, 5)
    ring = sorted(h3.grid_ring(start_cell, k_cells_away))[:count]
    return [h3.cell_to_latlng(c) for c in ring]


# --- the loop ---------------------------------------------------------------


def test_k_grows_by_one_to_four_then_by_two_to_fifteen():
    assert k_steps(Settings()) == [1, 2, 3, 4, 6, 8, 10, 12, 14, 15]


def _fake_loop(direct_at_k: dict[int, int]):
    """search_band/label_hits fakes: `direct_at_k[k]` direct Facilities in the band at ring k."""
    start = h3.latlng_to_cell(*PATNA, 5)
    searched_bands = []

    def search_band(cells):
        searched_bands.append(set(cells))
        hits = []
        for k, count in direct_at_k.items():
            for i, cell in enumerate(sorted(h3.grid_ring(start, k))[:count]):
                if cell in cells:
                    hits.append({"item_id": f"{k}-{i}", "unique_id": f"f{k}-{i}", "item_type": "equipment", "item_text": "x", "h3_r5": cell, "similarity": 0.95})
        return hits

    def label_hits(hits):
        return {h["item_id"]: {"label": "direct", "reason": ""} for h in hits}, {"cache_hits": 0, "llm_calls": 1, "fallback_used": False}

    return search_band, label_hits, searched_bands


def test_the_loop_stops_once_three_facilities_have_a_direct_hit():
    search_band, label_hits, _ = _fake_loop({2: 2, 3: 1, 6: 5})

    found = expanding_search(*PATNA, search_band, label_hits)

    assert found["stop_reason"] == ENOUGH
    assert found["searched_k"] == 3
    assert len(found["rounds"]) == 3


def test_the_loop_reaches_max_k_when_nothing_direct_is_found():
    search_band, label_hits, _ = _fake_loop({})

    found = expanding_search(*PATNA, search_band, label_hits)

    assert found["stop_reason"] == MAX_RADIUS
    assert found["searched_k"] == 15
    assert found["searched_radius_km"] > 200


def test_each_round_searches_only_the_new_band_of_cells():
    search_band, label_hits, bands = _fake_loop({})

    expanding_search(*PATNA, search_band, label_hits)

    start = h3.latlng_to_cell(*PATNA, 5)
    assert bands[0] == set(h3.grid_disk(start, 1))
    for earlier, later in zip(bands, bands[1:]):
        assert not earlier & later
    assert set().union(*bands) == set(h3.grid_disk(start, 15))
    assert bands[4] == set(h3.grid_disk(start, 6)) - set(h3.grid_disk(start, 4))


def test_hits_below_min_similarity_are_dropped_before_labelling():
    sent = []

    def search_band(cells):
        return [{"item_id": "a", "unique_id": "f", "item_type": "equipment", "item_text": "x", "h3_r5": cells[0], "similarity": 0.6}]

    def label_hits(hits):
        sent.extend(hits)
        return {}, {"cache_hits": 0, "llm_calls": 0, "fallback_used": False}

    found = expanding_search(*PATNA, search_band, label_hits)

    assert sent == [] and found["hits"] == []


# --- recommend() --------------------------------------------------------------


def test_a_rural_start_point_widens_until_it_finds_a_match_and_reports_the_radius():
    (lat, lon), = ring_points(9, 1)
    backend = FakeBackend([facility_at(lat, lon, "far")], {"far": ("equipment", "4 hemodialysis machines", 0.95)})

    result = recommend("dialysis", f"{PATNA[0]},{PATNA[1]}", backend=backend)

    assert result["status"] == "ok"
    assert [r["unique_id"] for r in result["top"]] == ["far"]
    assert result["search"]["searched_k"] == 15
    assert result["search"]["stop_reason"] == MAX_RADIUS
    assert result["search"]["searched_radius_km"] > 200
    assert result["top"][0]["distance_km"] > 100
    assert result["top"][0]["evidence"][0]["item_text"] == "4 hemodialysis machines"


def test_top_three_and_the_next_three_by_rank():
    points = ring_points(1, 6)
    facilities = [facility_at(lat, lon, f"f{i}") for i, (lat, lon) in enumerate(points)]
    sims = [0.99, 0.98, 0.97, 0.96, 0.95, 0.94]
    texts = {f"f{i}": ("capability" if i < 3 else "specialty", "dialysis", sims[i]) for i in range(6)}
    backend = FakeBackend(facilities, texts)

    result = recommend("dialysis", "Patna", backend=backend)

    # Capability hits outweigh specialty hits; distances differ a little, so order within each group may vary.
    assert {r["unique_id"] for r in result["top"]} == {"f0", "f1", "f2"}
    assert {r["unique_id"] for r in result["others"]} == {"f3", "f4", "f5"}
    ranks = [r["rank"] for r in result["top"] + result["others"]]
    assert ranks == sorted(ranks, reverse=True)
    assert result["search"]["stop_reason"] == ENOUGH
    assert result["evidence_checked"] is True


def test_a_second_identical_query_uses_the_label_cache():
    (lat, lon), = ring_points(1, 1)
    backend = FakeBackend([facility_at(lat, lon, "f")], {"f": ("equipment", "Dialysis unit", 0.95)})

    first = recommend("Dialysis", "800001", backend=backend)
    calls = backend.chat_calls
    second = recommend("  dialysis ", "800001", backend=backend)

    assert calls >= 1
    assert backend.chat_calls == calls
    assert second["top"] == first["top"]
    assert sum(r["cache_hits"] for r in second["round_details"]) >= 1


def test_an_llm_failure_falls_back_to_similarity_and_is_marked_evidence_not_checked():
    (lat, lon), = ring_points(1, 1)
    backend = FakeBackend([facility_at(lat, lon, "f")], {"f": ("equipment", "Dialysis unit", 0.85)}, llm_fails=True)

    result = recommend("dialysis", "Patna", backend=backend)

    assert result["evidence_checked"] is False
    evidence = result["top"][0]["evidence"][0]
    assert evidence["label"] == "related" and evidence["checked"] is False
    assert backend.cache == {}  # fallback labels are never cached


def test_unrelated_hits_do_not_make_results():
    (lat, lon), = ring_points(1, 1)
    backend = FakeBackend([facility_at(lat, lon, "f")], {"f": ("equipment", "CT scanner", 0.85)}, llm_labels={"f-e0": "unrelated"})

    result = recommend("dialysis", "Patna", backend=backend)

    assert result["status"] == "ok" and result["top"] == []
    assert result["search"]["stop_reason"] == MAX_RADIUS


def test_result_carries_warnings_and_good_points_from_flags():
    (lat, lon), = ring_points(1, 1)
    f = facility_at(lat, lon, "f", flag_has_government_source=True, flag_coords_shared=True, flag_own_site_in_sources=False)
    backend = FakeBackend([f], {"f": ("equipment", "Dialysis unit", 0.95)})

    top = recommend("dialysis", "Patna", backend=backend)["top"][0]

    assert top["good_points"] == ["Listed on a government website"]
    assert top["location_approximate"] is True
    assert top["warnings"][0].startswith("Location may be inaccurate")


def test_an_ambiguous_location_returns_candidates():
    class Ambiguous(FakeBackend):
        def district_places(self, name, state):
            return [Place("Aurangabad, Bihar", "district", 24.7, 84.3, "BIHAR"), Place("Aurangabad, Maharashtra", "district", 19.9, 75.3, "MAHARASHTRA")]

    result = recommend("MRI", "Aurangabad", backend=Ambiguous([], {}))

    assert result["status"] == "ambiguous"
    assert result["candidates"] == ["Aurangabad, Bihar", "Aurangabad, Maharashtra"]


@pytest.mark.parametrize("location", ["Atlantis", "999999", ""])
def test_an_unknown_location_is_a_clear_error(location):
    result = recommend("MRI", location, backend=FakeBackend([], {}))

    assert result["status"] == "error" and result["error"]


def test_rounds_list_each_band_and_the_facilities_checked_in_it_with_their_best_label():
    (near_lat, near_lon), = ring_points(1, 1)
    (mid_lat, mid_lon), = ring_points(3, 1)
    (far_lat, far_lon), = ring_points(5, 1)
    backend = FakeBackend(
        [facility_at(near_lat, near_lon, "near"), facility_at(mid_lat, mid_lon, "mid"), facility_at(far_lat, far_lon, "far")],
        {"near": ("equipment", "CT scanner", 0.85), "mid": ("capability", "Dialysis", 0.95), "far": ("procedure", "Hemodialysis", 0.95)},
        llm_labels={"near-e0": "unrelated", "mid-e0": "related"},
    )

    result = recommend("dialysis", "Patna", backend=backend)

    rounds = result["rounds"]
    assert [r["k"] for r in rounds] == [1, 2, 3, 4, 6, 8, 10, 12, 14, 15]
    start = h3.latlng_to_cell(*PATNA, 5)
    assert set(rounds[0]["cells"]) == set(h3.grid_disk(start, 1))
    assert rounds[0]["facilities"] == [{"unique_id": "near", "lat": near_lat, "lon": near_lon, "label": None}]
    assert rounds[2]["facilities"] == [{"unique_id": "mid", "lat": mid_lat, "lon": mid_lon, "label": "related"}]
    assert rounds[4]["facilities"] == [{"unique_id": "far", "lat": far_lat, "lon": far_lon, "label": "direct"}]
    assert rounds[1]["facilities"] == []


def test_a_repeat_makes_no_llm_call_even_when_more_hits_than_are_sent_were_found():
    points = ring_points(1, 6) + ring_points(2, 12)
    facilities = [facility_at(lat, lon, f"f{i}") for i, (lat, lon) in enumerate(points)]
    backend = FakeBackend(facilities, {f"f{i}": ("capability", "Dialysis", 0.95 - i * 0.001) for i in range(18)}, llm_labels={f"f{i}-e0": "related" for i in range(18)})

    recommend("dialysis", "Patna", backend=backend)
    calls = backend.chat_calls
    recommend("dialysis", "Patna", backend=backend)

    assert backend.chat_calls == calls


def test_progress_events_show_each_round_being_searched_found_and_checked():
    (near_lat, near_lon), = ring_points(1, 1)
    (far_lat, far_lon), = ring_points(3, 1)
    backend = FakeBackend(
        [facility_at(near_lat, near_lon, "near"), facility_at(far_lat, far_lon, "far")],
        {"near": ("equipment", "CT scanner", 0.85), "far": ("capability", "Dialysis", 0.95)},
        llm_labels={"near-e0": "unrelated"},
    )
    events = []

    recommend("dialysis", "Patna", backend=backend, on_progress=events.append)

    assert events[0]["type"] == "located" and events[0]["label"] == "Patna, Bihar"
    assert [e["type"] for e in events[1:4]] == ["band", "found", "checked"]
    assert [c["unique_id"] for c in events[2]["candidates"]] == ["near"]
    assert events[3]["labels"] == {"near": None}  # ruled out
    round3 = [e for e in events if e.get("round") == 3]
    assert round3[2]["labels"] == {"far": "direct"} and round3[2]["direct_so_far"] == 1
    assert sum(1 for e in events if e["type"] == "band") == 10


def test_a_broken_progress_callback_does_not_break_the_search():
    (lat, lon), = ring_points(1, 1)
    backend = FakeBackend([facility_at(lat, lon, "f")], {"f": ("equipment", "Dialysis unit", 0.95)})

    def broken(event):
        raise RuntimeError("chart failed")

    result = recommend("dialysis", "Patna", backend=backend, on_progress=broken)

    assert result["status"] == "ok" and [r["unique_id"] for r in result["top"]] == ["f"]


def _same_place_pair(**second):
    """Two Facilities at one point with the same claim; the second gets `second`'s columns."""
    lat, lon = PATNA
    facilities = [facility_at(lat, lon, "private"), facility_at(lat, lon, "free", **second)]
    texts = {uid: ("equipment", "Dialysis unit", 0.95) for uid in ("private", "free")}
    return facilities, texts


def test_a_government_facility_ranks_a_little_higher_where_few_households_are_insured():
    facilities, texts = _same_place_pair(affordability="government")
    area = {"nfhs_state": "Bihar", "nfhs_district": "Patna", "insurance_pct": 20.0}

    result = recommend("dialysis", "Patna", backend=FakeBackend(facilities, texts, area=area))

    free, private = result["top"]
    assert (free["unique_id"], private["unique_id"]) == ("free", "private")
    assert free["affordability_factor"] == 1.12  # 1 + 0.15 × 1.0 × 0.8
    assert private["affordability_factor"] == 1.0
    assert free["rank"] == round(private["rank"] * 1.12, 4)
    assert result["area"] == area and result["uninsured_share"] == 0.8


def test_tiers_rank_government_then_charitable_then_public():
    lat, lon = PATNA
    tiers = ["public", "charitable", "government", None]
    facilities = [facility_at(lat, lon, f"f{i}", affordability=t) for i, t in enumerate(tiers)]
    texts = {f"f{i}": ("equipment", "Dialysis unit", 0.95) for i in range(len(tiers))}

    result = recommend("dialysis", "Patna", backend=FakeBackend(facilities, texts, area={"insurance_pct": 50.0}))

    assert [r["affordability"] for r in result["top"] + result["others"]] == ["government", "charitable", "public", None]


def test_without_an_area_figure_the_national_uninsured_share_is_used():
    facilities, texts = _same_place_pair(affordability="government")

    for area in (None, TimeoutError("warehouse down")):
        result = recommend("dialysis", "Patna", backend=FakeBackend(facilities, texts, area=area))

        assert result["status"] == "ok" and result["area"] is None
        assert result["uninsured_share"] == 0.59
        assert result["top"][0]["affordability_factor"] == round(1 + 0.15 * 0.59, 3)


# --- healthcare desert (#46) ------------------------------------------------------


def test_a_direct_match_within_the_threshold_is_not_a_desert():
    (lat, lon), = ring_points(6, 1)
    backend = FakeBackend([facility_at(lat, lon, "f")], {"f": ("equipment", "Dialysis unit", 0.95)})

    desert = recommend("dialysis", "Patna", "planned", backend=backend)["desert"]

    assert desert["is_desert"] is False
    assert desert["rings_needed"] == 6 and desert["threshold_k"] == 6
    assert desert["nearest_direct_km"] > 50


def test_needing_more_rings_than_the_threshold_is_a_desert():
    (lat, lon), = ring_points(7, 1)
    backend = FakeBackend([facility_at(lat, lon, "f")], {"f": ("equipment", "Dialysis unit", 0.95)})

    desert = recommend("dialysis", "Patna", "planned", backend=backend)["desert"]

    # Ring 7 is searched in the k=8 band; rings needed is the true grid distance, not the band.
    assert desert["is_desert"] is True and desert["rings_needed"] == 7


def test_the_threshold_depends_on_urgency():
    (lat, lon), = ring_points(3, 1)
    backend = FakeBackend([facility_at(lat, lon, "f")], {"f": ("equipment", "Dialysis unit", 0.95)})

    assert recommend("dialysis", "Patna", "emergency", backend=backend)["desert"]["is_desert"] is True
    assert recommend("dialysis", "Patna", "planned", backend=backend)["desert"]["is_desert"] is False


def test_only_direct_matches_count_against_a_desert():
    (near_lat, near_lon), = ring_points(1, 1)
    backend = FakeBackend([facility_at(near_lat, near_lon, "near")], {"near": ("specialty", "nephrology", 0.95)}, llm_labels={"near-e0": "related"})

    result = recommend("dialysis", "Patna", backend=backend)

    assert [r["unique_id"] for r in result["top"]] == ["near"]
    assert result["desert"] == {**result["desert"], "is_desert": True, "rings_needed": None, "nearest_direct_km": None}


def test_nothing_found_out_to_max_k_is_a_desert():
    desert = recommend("dialysis", "Patna", backend=FakeBackend([], {}))["desert"]

    assert desert["is_desert"] is True and desert["rings_needed"] is None
