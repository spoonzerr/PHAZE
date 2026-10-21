"""Alerts: the places you watch, how you're told, and what's been sent."""

from __future__ import annotations

import json

import streamlit as st

from phaze import state, ui
from phaze.cities import city_key
from phaze.data import geocode
from phaze.notify import send_telegram, telegram_configured


def _add_place():
    ss = st.session_state
    q = st.text_input("City name", placeholder="Pekanbaru")
    if st.button("Search", icon=":material/search:") and q:
        ss.geo_results = geocode(q)
        if not ss.geo_results:
            st.error("No match, or the place search is offline. Check the spelling and try again.")
    if ss.geo_results:
        labels = [f"{g['name']}, {g['admin'] + ', ' if g['admin'] else ''}{g['country']}" for g in ss.geo_results]
        i = st.selectbox("Which one?", range(len(labels)), format_func=lambda k: labels[k])
        if st.button("Add to my places", type="primary", icon=":material/add:"):
            g = ss.geo_results[i]
            if city_key(g) not in [city_key(c) for c in state.all_cities()]:
                ss.custom_cities.append(g)
            ss.watchlist = list(dict.fromkeys(ss.watchlist + [city_key(g)]))
            ss.geo_results = []
            st.cache_data.clear()
            st.rerun()


def render():
    ss = st.session_state
    st.html(ui.page_head("Your alerts",
                         f"PHAZE keeps an eye on the places you pick and tells you when the air goes above "
                         f"{ss.threshold}. Change that limit in the sidebar."))

    left, right = st.columns([1.3, 1], gap="large")
    with left:
        st.html(ui.section("Places you watch"))
        options = [city_key(c) for c in state.all_cities()]
        chosen = st.multiselect("Places you watch", options, default=[w for w in ss.watchlist if w in options],
                                label_visibility="collapsed", placeholder="Pick places to watch")
        if chosen != ss.watchlist:
            ss.watchlist = chosen
            st.rerun()
        with st.popover("Add any city in the world", icon=":material/add_location_alt:"):
            _add_place()
        readings = state.readings()
        if readings:
            st.html(ui.watch_rows(readings, ss.threshold))

    with right:
        st.html(ui.section("How you're told"))
        with st.container(border=True):
            auto = st.toggle("Check automatically while PHAZE is open", value=ss.auto_check)
            every = st.select_slider("How often", options=[1, 5, 10, 15, 30], value=ss.check_every,
                                     format_func=lambda m: f"Every {m} min", disabled=not auto)
            if (auto, every) != (ss.auto_check, ss.check_every):
                ss.auto_check, ss.check_every = auto, every
                st.rerun()
            ready = telegram_configured()
            push = st.toggle("Also send alerts to my phone (Telegram)", value=ss.push and ready, disabled=not ready,
                             help="Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env. The README shows how.")
            if push != ss.push and ready:
                ss.push = push
            with st.container(horizontal=True, gap="small"):
                if st.button("Send a test message", icon=":material/send:", disabled=not ready):
                    ok, msg = send_telegram("PHAZE test: phone alerts are working.")
                    st.toast("Test message sent" if ok else msg, icon=":material/check:" if ok else ":material/error:")
                if st.button("Check now", icon=":material/refresh:"):
                    st.rerun()
            watch_json = json.dumps({
                "threshold": ss.threshold, "profile": ss.profile, "cities": ss.watchlist,
                "custom_cities": [c for c in ss.custom_cities if city_key(c) in ss.watchlist],
            }, indent=2)
            st.download_button("Download my watchlist", watch_json, "watchlist.json", "application/json",
                               icon=":material/download:",
                               help="Use it with notifier.py to get phone alerts even when PHAZE is closed.")
            if not ready:
                st.html('<p class="ph-note">Phone alerts are off. Add a Telegram bot to .env to switch them on.</p>')

    st.space("medium")
    st.html(ui.section("Alert history", "Newest first. Each one is written for whoever you set in the sidebar."))
    if ss.alert_log:
        st.html(ui.alert_timeline(ss.alert_log[:25]))
    else:
        st.html(ui.empty("No alerts yet",
                         f"You'll get one the moment a place you watch goes above {ss.threshold}."))
