"""Plan: the next 48 hours, and the clearest times for what you want to do."""

from __future__ import annotations

import streamlit as st

from phaze import charts, state, ui
from phaze.agents import ACTIVITIES, plan_outdoors
from phaze.cities import city_key


def render():
    ss = st.session_state
    st.html(ui.page_head("Plan around the haze",
                         "See the next 48 hours, then let PHAZE find the clearest times for what you have planned."))

    options = [city_key(c) for c in state.all_cities()]
    c1, c2 = st.columns([1, 1.7], gap="large", vertical_alignment="bottom")
    key = c1.selectbox("Place", options, index=options.index(ss.home) if ss.home in options else 0)
    activity = c2.pills("What are you planning?", ACTIVITIES, default=ss.get("plan_activity", ACTIVITIES[0]),
                        required=True) or ACTIVITIES[0]
    ss.plan_activity = activity

    fc = state.forecasts([key]).get(key, {})
    name = state.short(key)
    st.html(ui.section(f"The next 48 hours in {name}",
                       "Each block is one hour, coloured by its forecast level."))
    st.html(ui.hours(fc.get("times", []), fc.get("us_aqi", []), ss.threshold))
    st.altair_chart(charts.forecast(fc.get("times", []), fc.get("us_aqi", []), ss.threshold), theme=None,
                    width="stretch")
    note = "Forecast US AQI from Copernicus CAMS via Open-Meteo. Singapore's official PSI isn't forecast hour by hour."
    if fc.get("source") == "sample":
        note += " Showing a saved sample forecast because the live feed can't be reached."
    st.html(f'<p class="ph-note">{ui.esc(note)}</p>')

    st.space("small")
    st.html(ui.section("When should I go?", f"PHAZE reads the forecast for {activity.lower()} in {name}."))
    if st.button("Find my best times", type="primary", icon=":material/auto_awesome:"):
        with st.spinner("Nemotron Super is reading the forecast..."):
            ss.plan = {"place": key, "activity": activity,
                       **plan_outdoors(ss.llm, name, fc, ss.profile, activity, ss.threshold)}
    result = ss.get("plan")
    if result and result["place"] == key and result["activity"] == activity:
        st.html(ui.plan(result))
