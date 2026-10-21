"""News: what's causing the haze, from the latest reporting."""

from __future__ import annotations

import os

import streamlit as st

from phaze import state, ui
from phaze.agents import haze_report

AREAS = ["Singapore and Malaysia", "Indonesia", "Thailand", "Northern India and Pakistan", "Southeast Asia"]


def render():
    ss = st.session_state
    st.html(ui.page_head("Why is it hazy?",
                         "PHAZE searches the latest news, then Nemotron Super explains what's going on, "
                         "with links to every source."))

    area = st.pills("Area", AREAS, default=ss.get("news_area", AREAS[0]), label_visibility="collapsed",
                    required=True) or AREAS[0]
    ss.news_area = area
    c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
    custom = c1.text_input("Or type any place", placeholder="Chiang Mai")
    target = custom.strip() or area
    go = c2.button("Get the latest", type="primary", icon=":material/travel_explore:", width="stretch")

    if not os.getenv("TAVILY_API_KEY"):
        st.html(ui.empty("Web search is off",
                         "Add a TAVILY_API_KEY to your .env file to search the latest haze news."))
        return

    if go:
        rows, _ = state.world()
        worst = sorted([r for r in rows if r["us_aqi"]], key=lambda r: -r["us_aqi"])[:5]
        note = "Current worst readings tracked by PHAZE: " + ", ".join(f"{r['name']} {round(r['us_aqi'])}" for r in worst)
        with st.spinner(f"Searching the news for {target}..."):
            ss.report = {"area": target, **haze_report(ss.llm, target, note)}

    rep = ss.get("report")
    if rep and rep["area"] == target:
        st.html(ui.report(rep))
    else:
        st.html(ui.empty(f"Ready when you are",
                         f"Press Get the latest for a short explanation of the haze in {target}: what's causing it, "
                         "what happens next, and the articles it comes from."))
