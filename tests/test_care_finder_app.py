"""The Streamlit app's states, rendered with a fake backend (ticket #29)."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import talaria.care_finder.backend as backend_module
import talaria.care_finder.search_map as search_map
from talaria.care_finder.location import Place
from tests.test_care_finder_recommend import FakeBackend, facility_at, ring_points

APP = str(Path(__file__).parent.parent / "app" / "app.py")


@pytest.fixture
def run_app(monkeypatch):
    def run(fake, service, location, urgency="Planned"):
        monkeypatch.setattr(backend_module, "DatabricksBackend", lambda: fake)
        monkeypatch.setattr(search_map, "STEP_SECONDS", 0)
        st.cache_data.clear()
        st.cache_resource.clear()
        at = AppTest.from_file(APP, default_timeout=30)
        at.run()
        at.text_input(key="service").input(service)
        at.text_input(key="location").input(location)
        at.button[0].click()
        at.run()
        assert not at.exception, at.exception
        return at

    return run


def _texts(at):
    return " ".join(
        [m.value for m in at.markdown] + [m.value for m in at.caption] + [w.value for w in at.warning]
        + [i.value for i in at.info] + [e.value for e in at.error] + [s.value for s in at.subheader]
    )


def test_results_show_cards_with_verbatim_quotes(run_app):
    (lat, lon), = ring_points(1, 1)
    fake = FakeBackend([facility_at(lat, lon, "f", official_phone="0612 222", flag_has_government_source=True)], {"f": ("equipment", "4 hemodialysis machines", 0.95)})

    at = run_app(fake, "dialysis", "Patna")

    text = _texts(at)
    assert "Hospital f" in text
    assert "4 hemodialysis machines" in text
    assert "Call to confirm: 0612 222" in text
    assert "✓ Listed on a government website" in text


def test_no_results_say_how_far_was_searched(run_app):
    at = run_app(FakeBackend([], {}), "dialysis", "Patna")

    assert "No facility with any evidence for dialysis was found within about" in _texts(at)


def test_ambiguous_location_asks_which_one(run_app):
    class Ambiguous(FakeBackend):
        def district_places(self, name, state):
            return [Place("Aurangabad, Bihar", "district", 24.7, 84.3, "BIHAR"), Place("Aurangabad, Maharashtra", "district", 19.9, 75.3, "MAHARASHTRA")]

    at = run_app(Ambiguous([], {}), "MRI", "Aurangabad")

    assert at.radio[0].label == "Did you mean…"
    assert at.radio[0].options == ["Aurangabad, Bihar", "Aurangabad, Maharashtra"]


def test_fallback_says_evidence_not_checked(run_app):
    (lat, lon), = ring_points(1, 1)
    fake = FakeBackend([facility_at(lat, lon, "f")], {"f": ("equipment", "Dialysis unit", 0.95)}, llm_fails=True)

    at = run_app(fake, "dialysis", "Patna")

    assert "Evidence not checked" in _texts(at)


def test_unknown_location_is_a_clear_error(run_app):
    at = run_app(FakeBackend([], {}), "MRI", "Atlantis")

    assert 'No PIN, district or city called "Atlantis" was found.' in _texts(at)


def test_search_map_ends_on_the_final_view_and_scrubs_and_replays(run_app):
    (lat, lon), = ring_points(3, 1)
    fake = FakeBackend([facility_at(lat, lon, "f")], {"f": ("equipment", "Dialysis unit", 0.95)})

    at = run_app(fake, "dialysis", "Patna")

    slider = at.slider(key="round_slider")
    assert slider.value == 10 and slider.max == 10
    assert "Done after 10 rounds" in _texts(at) and "1. Hospital f" in _texts(at)
    slider.set_value(3).run()
    assert "Round 3 · 1 confirmed, 0 related, 0 ruled out · 1 confirmed so far" in _texts(at)
    slider.set_value(2).run()
    assert "Round 2 · 0 confirmed, 0 related, 0 ruled out · 0 confirmed so far" in _texts(at)
    next(b for b in at.button if b.label == "Replay search").click().run()
    assert not at.exception
    assert "Done after 10 rounds" in _texts(at)


def test_the_map_is_reset_for_an_ambiguous_location(run_app):
    class Ambiguous(FakeBackend):
        def district_places(self, name, state):
            return [Place("Aurangabad, Bihar", "district", 24.7, 84.3, "BIHAR"), Place("Aurangabad, Maharashtra", "district", 19.9, 75.3, "MAHARASHTRA")]

    at = run_app(Ambiguous([], {}), "MRI", "Aurangabad")

    assert "Round 1" not in _texts(at) and "Done after" not in _texts(at)
    assert at.radio[0].label == "Did you mean…"


def test_a_far_match_shows_the_healthcare_desert_alert(run_app):
    (lat, lon), = ring_points(9, 1)
    at = run_app(FakeBackend([facility_at(lat, lon, "far")], {"far": ("equipment", "Dialysis unit", 0.95)}), "dialysis", "Patna")

    assert any(e.value.startswith("Possible healthcare desert") for e in at.error)
    assert "Confirm locally before acting" in _texts(at)


def test_a_near_match_shows_no_desert_alert(run_app):
    (lat, lon), = ring_points(1, 1)
    at = run_app(FakeBackend([facility_at(lat, lon, "f")], {"f": ("equipment", "Dialysis unit", 0.95)}), "dialysis", "Patna")

    assert not any("healthcare desert" in e.value for e in at.error)
