"""The animated search map (ticket #33): one pydeck frame per search round.

`frame(answer, i)` draws the searched H3 cells up to round `i` (newest band
highlighted, earlier bands faded), the Facilities checked so far coloured by
result, and the user's point; the last frame also labels the top 3.
"""

import math

import pydeck as pdk

COLORS = {
    "direct": [0, 140, 70],
    "related": [235, 135, 0],
    None: [140, 140, 140],
    "you": [30, 90, 220],
}
LEGEND = "🟢 Says it offers this (ringed) · 🟠 Related mention · ⚪ Checked, no match · 🔵 You · shaded hexagons: area searched, newest ring darker"
NEWEST_BAND = [235, 135, 0, 90]
EARLIER_BAND = [30, 90, 220, 28]
FRAME_SECONDS = 0.6


def caption(answer: dict, i: int) -> str:
    rounds = answer["rounds"]
    direct = sum(1 for r in rounds[: i + 1] for f in r["facilities"] if f["label"] == "direct")
    matches = "match" if direct == 1 else "matches"
    return f"Round {i + 1} · {rounds[i]['radius_km']:.0f} km · {direct} direct {matches} so far"


def _zoom(radius_km: float) -> float:
    """A fixed zoom that fits the final search radius, so the camera stays still while the ring grows."""
    return max(4.0, min(11.0, 9.3 - math.log2(max(radius_km, 5.0) / 10.0)))


def frame(answer: dict, i: int) -> pdk.Deck:
    rounds = answer["rounds"]
    me = answer["location"]
    cells = [
        {"cell": cell, "color": NEWEST_BAND if n == i else EARLIER_BAND}
        for n, r in enumerate(rounds[: i + 1])
        for cell in r["cells"]
    ]
    checked = [{**f, "color": COLORS[f["label"]], "radius": 1600 if f["label"] == "direct" else 1100 if f["label"] else 650} for r in rounds[: i + 1] for f in r["facilities"]]
    layers = [
        pdk.Layer("H3HexagonLayer", cells, get_hexagon="cell", get_fill_color="color", stroked=True, get_line_color=[255, 255, 255, 120], line_width_min_pixels=1, extruded=False, pickable=False),
        pdk.Layer("ScatterplotLayer", checked, get_position=["lon", "lat"], get_fill_color="color", get_radius="radius", radius_min_pixels=3, opacity=0.9),
        # The "ping": an outline ring around each direct match.
        pdk.Layer(
            "ScatterplotLayer",
            [f for f in checked if f["label"] == "direct"],
            get_position=["lon", "lat"],
            get_radius=3800,
            radius_min_pixels=8,
            stroked=True,
            filled=False,
            get_line_color=COLORS["direct"],
            line_width_min_pixels=2,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            [{"lat": me["lat"], "lon": me["lon"]}],
            get_position=["lon", "lat"],
            get_fill_color=COLORS["you"],
            get_radius=1500,
            radius_min_pixels=7,
            stroked=True,
            get_line_color=[255, 255, 255],
            line_width_min_pixels=2,
        ),
    ]
    if i == len(rounds) - 1 and answer["top"]:
        labels = [{"lat": r["latitude"], "lon": r["longitude"], "text": f"{n}. {r['name']}"} for n, r in enumerate(answer["top"], 1)]
        layers.append(pdk.Layer("TextLayer", labels, get_position=["lon", "lat"], get_text="text", get_size=13, get_color=[20, 20, 20], get_pixel_offset=[0, -18], background=True, get_background_color=[255, 255, 255, 220]))
    view = pdk.ViewState(latitude=me["lat"], longitude=me["lon"], zoom=_zoom(rounds[-1]["radius_km"]))
    return pdk.Deck(layers=layers, initial_view_state=view, map_provider="carto", map_style="light")
