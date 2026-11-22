"""Care finder: a Streamlit Databricks App on top of `recommend()` (ticket #29).

Local run, from the repo root:  uv run streamlit run app/app.py
Every line on a card comes from `talaria.care_finder.present` templates.
"""

import os
import sys
import time

# From the repo, the package and config.py are one folder up; in the deployed app
# they are copied next to this file (see scripts/deploy_app.sh).
_HERE = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(os.path.join(_HERE, "config.py")):
    sys.path.insert(0, os.path.dirname(_HERE))

import pandas as pd
import streamlit as st

from talaria.care_finder import present
from talaria.care_finder.recommend import recommend

EXAMPLES = ["Dialysis", "Emergency C-section", "NICU", "MRI", "Cardiac surgery", "Burn care"]

st.set_page_config(page_title="Find care nearby", page_icon="🏥", layout="centered")


@st.cache_resource
def backend():
    from talaria.care_finder.backend import DatabricksBackend

    return DatabricksBackend()


def answer_for(query: tuple) -> dict:
    """The answer for this query, computed once per search, then kept in the
    session while the user expands sections."""
    if st.session_state.get("answer_query") != query:
        st.session_state.answer = recommend(*query, backend=backend())
        st.session_state.answer_query = query
    return st.session_state.answer


def md(text: str) -> str:
    """Escape Markdown so a quote shows exactly as written."""
    return "".join("\\" + c if c in "\\`*_{}[]<>()#+-.!|~$" else c for c in str(text))


def run_search(service: str, location: str, urgency: str) -> None:
    st.session_state.query = (service, location, urgency)
    st.session_state.pop("answer_query", None)  # pressing Search always searches again


# --- Search form -------------------------------------------------------------

st.title("Find care nearby")
st.caption("Enter a service and a place. We look for facilities whose own records say they offer it, nearest first.")

example = st.pills("Examples", EXAMPLES, key="example", label_visibility="collapsed")
if example and st.session_state.get("last_example") != example:
    st.session_state.service = example
    st.session_state.last_example = example

with st.form("search"):
    service = st.text_input("Service", key="service", placeholder="e.g. dialysis, MRI, NICU")
    location = st.text_input("Location", key="location", placeholder="PIN, city, district or lat,lon (e.g. 800001)")
    urgency = st.segmented_control("Urgency", ["Planned", "Emergency"], default="Planned", key="urgency")
    if st.form_submit_button("Search", type="primary", width="stretch"):
        run_search(service, location, (urgency or "Planned").lower())

if "query" not in st.session_state:
    st.stop()

service, location, urgency = st.session_state.query
with st.spinner(f"Searching for {service} near {location}…"):
    answer = answer_for((service, location, urgency))

# --- Error and ambiguous states -----------------------------------------------

if answer["status"] == "error":
    st.error(answer["error"])
    st.stop()

if answer["status"] == "ambiguous":
    st.warning(f'"{location}" matches more than one place.')
    choice = st.radio("Did you mean…", answer["candidates"], index=None)
    if choice and st.button("Search there", type="primary"):
        st.session_state.query = (service, choice, urgency)
        st.rerun()
    st.stop()

# --- Results ----------------------------------------------------------------------

if not answer["evidence_checked"]:
    st.warning(present.NOT_CHECKED, icon="⚠️")

top, others = answer["top"], answer["others"]
(st.info if top and top[0]["evidence_band"] == "strong" else st.warning)(present.summary(answer))
st.caption(present.search_extent(answer))


def card(result: dict, position: int) -> None:
    with st.container(border=True):
        st.subheader(md(present.heading(result, position)), anchor=False)
        st.caption(present.subheading(result))
        st.markdown(f"**{present.evidence_line(result, answer['service'])}** · {present.confidence_line(result)}")

        st.markdown("**Why**")
        for line in present.why_lines(result):
            st.markdown(f"- {line['type']}: “{md(line['quote'])}”  \n  _{line['label']}: {md(line['reason'])}_")

        for line in result["good_points"]:
            st.markdown(f"✓ {line}")
        for line in result["warnings"]:
            st.markdown(f"⚠ {line}")

        if call := present.call_line(result):
            st.markdown(f"📞 **{call}**")
        address = present.address_line(result)
        if address:
            st.caption(address)
        links = [result["official_website"]] if result.get("official_website") else []
        links += [u for u in result["source_urls"] if u not in links]
        if links:
            st.caption("Sources: " + " · ".join(f"[{i}]({u})" for i, u in enumerate(links[:5], 1)))

        with st.expander("How we decided"):
            st.dataframe(pd.DataFrame(present.score_parts(result)), hide_index=True, width="stretch")
            hits = pd.DataFrame(result["evidence"])[["item_type", "item_text", "similarity", "label", "value", "counted"]]
            st.dataframe(hits, hide_index=True, width="stretch")
            st.code(present.formula_text(answer), language=None)
            st.json({k: answer["settings"][k] for k in ("min_direct_facilities", "max_k", "min_similarity", "type_weights", "label_values")}, expanded=False)


for i, result in enumerate(top, 1):
    card(result, i)

# --- Map -------------------------------------------------------------------------
# The map slot comes first on the page, but is filled last: the cards and the other
# options show at once, then the search replays underneath the cards.

map_slot = st.container()

if others:
    with st.expander("Other options we considered"):
        for result in others:
            st.markdown(f"- {md(present.other_line(result, top[-1] if top else None))}")


def static_map() -> None:
    points = [{"lat": answer["location"]["lat"], "lon": answer["location"]["lon"], "color": "#1e5adc", "size": 300}]
    points += [{"lat": r["latitude"], "lon": r["longitude"], "color": "#008c46", "size": 200} for r in top]
    points += [{"lat": r["latitude"], "lon": r["longitude"], "color": "#eb8700", "size": 120} for r in others]
    st.map(pd.DataFrame(points), color="color", size="size")
    st.caption("Blue: your location · Green: top results · Orange: other options")


def search_map() -> None:
    from talaria.care_finder import search_map as sm

    rounds = answer["rounds"]
    last = len(rounds) - 1
    st.markdown("**How the search grew**")
    chart, label = st.empty(), st.empty()
    st.caption(sm.LEGEND)
    replay_col, slider_col = st.columns([1, 3], vertical_alignment="bottom")
    replay = replay_col.button("Replay search", width="stretch")
    query = st.session_state.query
    if replay or st.session_state.get("animated_for") != query:
        st.session_state.animated_for = query
        for i in range(last + 1):
            chart.pydeck_chart(sm.frame(answer, i), height=420)
            label.caption(sm.caption(answer, i))
            time.sleep(sm.FRAME_SECONDS)
        st.session_state.round_slider = last + 1
    if last == 0:
        chosen = 1
    else:
        default = {} if "round_slider" in st.session_state else {"value": last + 1}
        chosen = slider_col.slider("Round", 1, last + 1, key="round_slider", **default)
    chart.pydeck_chart(sm.frame(answer, chosen - 1), height=420)
    label.caption(sm.caption(answer, chosen - 1) + (f" · {sm.top_names(answer)}" if chosen - 1 == last and top else ""))


with map_slot:
    if answer.get("rounds"):
        search_map()
    else:  # an answer without rounds, e.g. from an older cache
        static_map()
