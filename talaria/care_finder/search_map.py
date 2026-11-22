"""The search map (ticket #33): the H3 search drawn live as it runs, and replayed after.

`SearchView` takes the progress events `recommend()` emits (`located`, then per
round `band`, `found`, `checked`) and draws the current state as a pydeck map:

- `band`: the round's new hexagons light up (earlier rounds fade).
- `found`: each Facility with a similar claim appears as a grey "checking" dot.
- `checked`: the dots are filtered: direct turns green with a ping ring, related
  orange, and the ruled-out ones shrink and fade.

`replay_events(answer)` rebuilds the same events from a finished answer, so the
replay and the round slider show exactly what the live search showed.
"""

import math

import h3
import pydeck as pdk

GREEN, ORANGE, BLUE = [0, 140, 70], [235, 135, 0], [30, 90, 220]
CHECKING = [90, 90, 90]
RULED_OUT = [160, 160, 160, 110]
NEWEST_BAND = [235, 135, 0, 95]
EARLIER_BAND = [30, 90, 220, 28]
DESERT_BAND = [210, 40, 40, 70]  # the area within the desert threshold, when it had no match (#46)
LEGEND = (
    "🟢 Says it offers this (ringed) · 🟠 Related mention · ⚫ Being checked · ⚪ Ruled out · 🔵 You · "
    "hexagons: area searched, newest ring orange, red where a possible healthcare desert was found"
)
STEP_SECONDS = 0.5  # pause per replayed step


class SearchView:
    def __init__(self, final_radius_km: float | None = None):
        self.me = None
        self.rounds: list[dict] = []  # {k, radius_km, cells, points: {uid: {lat, lon, label, checked}}}
        self.stage = None
        self.direct_so_far = 0
        self.final_radius_km = final_radius_km
        self.top: list[dict] = []
        self.desert_cells: set[str] = set()

    # --- events -------------------------------------------------------

    def apply(self, event: dict) -> None:
        kind = event["type"]
        if kind == "located":
            self.me = {"lat": event["lat"], "lon": event["lon"], "label": event["label"]}
        elif kind == "band":
            self.rounds.append({"k": event["k"], "radius_km": event["radius_km"], "cells": event["cells"], "points": {}})
        elif kind == "found":
            self.rounds[-1]["points"] = {
                c["unique_id"]: {"lat": c["lat"], "lon": c["lon"], "label": None, "checked": False} for c in event["candidates"]
            }
        elif kind == "checked":
            for uid, label in event["labels"].items():
                point = self.rounds[-1]["points"].get(uid)
                if point is not None:
                    point.update(label=label, checked=True)
            self.direct_so_far = event["direct_so_far"]
        self.stage = kind

    def finish(self, top: list[dict], desert: dict | None = None) -> None:
        """The final view: the top results numbered, and the desert area tinted red when there is one."""
        self.top = top
        if desert and desert["is_desert"]:
            self.desert_cells = set(h3.grid_disk(desert["start_cell"], desert["threshold_k"]))
        self.stage = "done"

    # --- drawing --------------------------------------------------------

    def caption(self) -> str:
        if not self.rounds:
            return f"Starting the search around {self.me['label']}…" if self.me else "Finding your location…"
        r, n = self.rounds[-1], len(self.rounds)
        points = list(r["points"].values())
        if self.stage == "band":
            return f"Round {n} · searching {len(r['cells'])} new map cells, out to about {r['radius_km']:.0f} km…"
        if self.stage == "found":
            return f"Round {n} · {len(points)} facilities mention something similar · checking the evidence…"
        direct = sum(1 for p in points if p["label"] == "direct")
        related = sum(1 for p in points if p["label"] == "related")
        ruled_out = len(points) - direct - related
        text = f"Round {n} · {direct} confirmed, {related} related, {ruled_out} ruled out · {self.direct_so_far} confirmed so far"
        if self.stage == "done":
            names = " · ".join(f"{i}. {t['name']}" for i, t in enumerate(self.top, 1))
            text = f"Done after {n} round{'s' if n != 1 else ''}, about {r['radius_km']:.0f} km · " + (names or "no match found")
        return text

    def deck(self) -> pdk.Deck:
        cells, dots, rings = [], [], []
        last = len(self.rounds) - 1
        for i, r in enumerate(self.rounds):
            colour = NEWEST_BAND if i == last and self.stage in ("band", "found") else EARLIER_BAND
            cells += [{"cell": c, "color": DESERT_BAND if c in self.desert_cells else colour} for c in r["cells"]]
            for p in r["points"].values():
                if not p["checked"]:
                    dots.append({**p, "color": CHECKING, "radius": 5})
                elif p["label"] == "direct":
                    dots.append({**p, "color": GREEN, "radius": 7})
                    rings.append(p)
                elif p["label"] == "related":
                    dots.append({**p, "color": ORANGE, "radius": 6})
                else:
                    dots.append({**p, "color": RULED_OUT, "radius": 3})
        layers = [
            pdk.Layer("H3HexagonLayer", cells, get_hexagon="cell", get_fill_color="color", stroked=True,
                      get_line_color=[255, 255, 255, 120], line_width_min_pixels=1, extruded=False),
            # Dots are sized in screen pixels, so they stay readable as the map zooms out.
            pdk.Layer("ScatterplotLayer", dots, get_position=["lon", "lat"], get_fill_color="color",
                      get_radius="radius", radius_units="'pixels'", stroked=True, get_line_color=[255, 255, 255],
                      line_width_min_pixels=1),
            # The "ping": an outline ring around each confirmed match.
            pdk.Layer("ScatterplotLayer", rings, get_position=["lon", "lat"], get_radius=13, radius_units="'pixels'",
                      stroked=True, filled=False, get_line_color=GREEN, line_width_min_pixels=2),
        ]
        if self.me:
            layers.append(pdk.Layer("ScatterplotLayer", [self.me], get_position=["lon", "lat"], get_fill_color=BLUE,
                                    get_radius=8, radius_units="'pixels'", stroked=True, get_line_color=[255, 255, 255],
                                    line_width_min_pixels=2))
        if self.stage == "done" and self.top:
            # Numbers only: names would overlap where Facilities cluster; the caption names them.
            labels = [{"lat": t["latitude"], "lon": t["longitude"], "text": str(i)} for i, t in enumerate(self.top, 1)]
            layers.append(pdk.Layer("TextLayer", labels, get_position=["lon", "lat"], get_text="text", get_size=16,
                                    get_color=[20, 20, 20], get_pixel_offset=[0, -20], background=True,
                                    get_background_color=[255, 255, 255, 230]))
        centre = self.me or {"lat": 22.5, "lon": 79.0}
        radius = self.final_radius_km or (self.rounds[-1]["radius_km"] if self.rounds else 30.0)
        view = pdk.ViewState(latitude=centre["lat"], longitude=centre["lon"], zoom=_zoom(radius) if self.me else 4)
        return pdk.Deck(layers=layers, initial_view_state=view, map_provider="carto", map_style="light")


def replay_events(answer: dict) -> list[dict]:
    """The events the live search emitted, rebuilt from a finished answer."""
    loc = answer["location"]
    events = [{"type": "located", "label": loc["label"], "lat": loc["lat"], "lon": loc["lon"]}]
    direct = 0
    for n, r in enumerate(answer["rounds"], 1):
        events.append({"type": "band", "round": n, "k": r["k"], "radius_km": r["radius_km"], "cells": r["cells"]})
        events.append({"type": "found", "round": n, "candidates": [{k: f[k] for k in ("unique_id", "lat", "lon")} for f in r["facilities"]]})
        direct += sum(1 for f in r["facilities"] if f["label"] == "direct")
        events.append({"type": "checked", "round": n, "labels": {f["unique_id"]: f["label"] for f in r["facilities"]}, "direct_so_far": direct})
    return events


def view_after_round(answer: dict, i: int) -> SearchView:
    """The map as it stood once round `i` (0-based) was checked; the last round shows the final view."""
    view = SearchView(answer["rounds"][-1]["radius_km"])
    for event in replay_events(answer):
        if event["type"] == "band" and event["round"] > i + 1:
            break
        view.apply(event)
    if i == len(answer["rounds"]) - 1:
        view.finish(answer["top"], answer.get("desert"))
    return view


def _zoom(radius_km: float) -> float:
    """A zoom that fits the search radius."""
    return max(4.0, min(11.0, 9.3 - math.log2(max(radius_km, 5.0) / 10.0)))
