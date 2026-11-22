"""Turn the user's location text into a point (#28 step 1).

`parse_location` says what kind of input it is; `choose_location` decides between
the candidate places the backend found. Both are pure.
"""

import re
from dataclasses import dataclass

_PIN = re.compile(r"^\s*(\d{3})\s?(\d{3})\s*$")
_COORDS = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Place:
    """A candidate place: `kind` is pin, district, city or coordinates."""

    label: str
    kind: str
    lat: float
    lon: float
    state: str | None = None


class LocationError(ValueError):
    """The location can't be understood or wasn't found; the message is shown to the user."""


def parse_location(text: str) -> tuple:
    """`("pin", "800001")`, `("coords", lat, lon)` or `("name", name, state_or_None)`.

    A name may carry its state after a comma ("Aurangabad, Bihar"), which is how a
    "Did you mean…" choice comes back.
    """
    text = (text or "").strip()
    if not text:
        raise LocationError("Enter a PIN, city, district or coordinates.")
    if pin := _PIN.match(text):
        return ("pin", pin.group(1) + pin.group(2))
    if coords := _COORDS.match(text):
        lat, lon = float(coords.group(1)), float(coords.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise LocationError(f"{text} isn't a valid latitude,longitude.")
        return ("coords", lat, lon)
    name, _, state = text.partition(",")
    return ("name", name.strip(), state.strip() or None)


def choose_location(text: str, districts: list[Place], cities: list[Place]) -> Place | list[Place]:
    """One place, or the candidates when the name means more than one place.

    A district name wins over a city name (the spec's order), so cities are only
    used when no district matches. Places in different states are ambiguous.
    """
    by_state: dict[str | None, Place] = {}
    for place in districts or cities:
        by_state.setdefault((place.state or "").upper(), place)
    candidates = list(by_state.values())
    if not candidates:
        raise LocationError(f'No PIN, district or city called "{text}" was found.')
    if len(candidates) == 1:
        return candidates[0]
    return sorted(candidates, key=lambda p: p.label)
