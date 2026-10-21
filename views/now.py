"""Now: the sky above your place, what it means for today, and your other places."""

from __future__ import annotations

import streamlit as st

from phaze import state, ui
from phaze.bands import band_for
from phaze.guidance import trend, verdicts
from phaze.watch import SINGAPORE, best_region, worst_region

WHO = {
    "General public": "the general public",
    "Sensitive (asthma, heart or lung condition)": "people with asthma or a heart or lung condition",
    "Elderly": "older people",
    "Children": "children",
    "Pregnant": "pregnant people",
}


def _heading_text(r: dict, fc: dict, tr) -> str:
    """One line on where a place's air is heading, from its forecast."""
    if r["index"] != "aqi" or tr.direction == "unknown" or not fc:
        return ""
    values, times = fc["us_aqi"], fc["times"]
    if tr.direction == "rising" and tr.peak is not None and tr.peak_index:
        return f"Up to about {round(tr.peak)} by {ui.fmt_time(times[tr.peak_index], with_day=True)}"
    ahead = [(v, i) for i, v in enumerate(values[:13]) if v is not None]
    if tr.direction == "easing" and ahead:
        low, i = min(ahead)
        return f"Down to about {round(low)} by {ui.fmt_time(times[i], with_day=True)}"
    if ahead:
        return f"Around {round(sum(v for v, _ in ahead) / len(ahead))} for the next 12 hours"
    return ""


def render():
    ss = st.session_state
    options = ss.watchlist or [SINGAPORE]
    if ss.home not in options:
        ss.home = options[0]

    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        pick = st.pills("Show the sky over", options, default=ss.home, format_func=state.short,
                        label_visibility="collapsed", required=True)
        st.page_link(state.PAGES["alerts"], label="Add a place", icon=":material/add:")
    if pick and pick != ss.home:
        ss.home = pick
        st.rerun()

    r = state.reading_for(ss.home)
    if r["index"] == "psi":
        psi = state.sg()
        meta = f"Official NEA reading: 24-hour PSI at {ui.fmt_time(psi['timestamp'])}, {ui.fmt_date(psi['timestamp'])}."
        (wn, wr), (bn, br) = worst_region(psi), best_region(psi)
        note = f"Highest in the {wn} ({wr.get('psi')}), lowest in the {bn} ({br.get('psi')})." if wn and wn != bn else ""
    else:
        meta = f"US AQI at {ui.fmt_time(r['time'])} local time, from Copernicus CAMS via Open-Meteo."
        note = ""
    if r.get("source") == "sample":
        note = (note + " " if note else "") + "Showing saved sample data because the live feed can't be reached."
    st.html(ui.sky(r["name"], r["value"], r["index"], meta=meta, note=note))

    band = band_for(r["value"], r["index"])
    st.html(ui.section("What this means today",
                       f"For {WHO.get(ss.profile, 'the general public')}, based on official health advice. "
                       "Not medical advice."))
    st.html(ui.today(verdicts(band.level, ss.profile)))

    left, right = st.columns([1, 1.45], gap="large")
    with left:
        if ss.home == SINGAPORE:
            psi = state.sg()
            st.html(ui.section("Across Singapore", f"24-hour PSI by region at {ui.fmt_time(psi['timestamp'])}."))
            st.html(ui.regions(psi))
        else:
            fc = state.forecasts([ss.home]).get(ss.home, {})
            st.html(ui.section(f"Next 48 hours in {r['name']}", "Forecast US AQI, one block per hour."))
            st.html(ui.hours(fc.get("times", []), fc.get("us_aqi", []), ss.threshold))
            st.page_link(state.PAGES["plan"], label="Find the clearest times", icon=":material/event_available:")

    with right:
        st.html(ui.section("Your places", "Right now, and where the forecast says each one is heading."))
        readings = state.readings()
        if not readings:
            st.html(ui.empty("No places yet", "Add the places you care about on the Alerts page."))
        else:
            fcs = state.forecasts([x["key"] for x in readings])
            rows = []
            for x in readings:
                fc = fcs.get(x["key"], {})
                values = fc.get("us_aqi", [])
                tr = trend(values)
                where = x["country"] if x["index"] == "aqi" else f"PSI, highest in the {x['region']}"
                rows.append({"name": x["name"], "where": where, "value": x["value"], "index": x["index"],
                             "forecast": values, "trend": tr, "peak_text": _heading_text(x, fc, tr)})
            st.html(ui.places(rows))

    st.space("medium")
    rows, _ = state.world()
    rank_col, key_col = st.columns([1.45, 1], gap="large")
    with rank_col:
        st.html(ui.section("Worst air in the world right now", f"US AQI across the {len(rows)} places PHAZE tracks."))
        st.html(ui.ranking(rows, limit=6))
        st.page_link(state.PAGES["map"], label="See them all on the map", icon=":material/public:")
    with key_col:
        st.html(ui.section("Reading the numbers",
                           "Singapore's PSI and the US AQI both run from 0 to 500. Above 100 is outside the healthy range."))
        st.html(ui.band_list("aqi"))
