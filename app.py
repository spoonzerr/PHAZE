"""PHAZE: haze is just a phase. Get alerted when the air leaves the healthy range.

Run:  streamlit run app.py

This file sets up the page, the sidebar and the background alert checker,
then hands over to the page you're on (see views/).
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from phaze import state, ui
from phaze.agents import PROFILES, write_alert
from phaze.bands import band_for
from phaze.notify import format_alert, send_telegram, telegram_configured
from views import alerts, ask, how, news, now, plan
from views import map as map_page

load_dotenv()
st.set_page_config(page_title="PHAZE", page_icon="static/phaze-icon.svg", layout="wide",
                   initial_sidebar_state="auto")  # open on computers, tucked away on phones
state.init()
ss = st.session_state
st.html(ui.css())
st.logo("static/phaze-logo.svg", icon_image="static/phaze-icon.svg", size="large")

# Alerts found by a timed background check are shown on the next full run.
# `full_run` tells the checker whether the rest of the page is still to be drawn in this run.
for toast in ss.pending_toasts:
    st.toast(toast["body"], icon=toast.get("icon"))
ss.pending_toasts = []
ss.full_run = True


def check_watchlist() -> tuple[list[dict], list[dict]]:
    readings = state.readings()
    new = []
    for rd in readings:
        if rd["value"] is None:
            continue
        band = band_for(rd["value"], rd["index"]).label
        if not ss.alert_state.should_alert(rd["key"], rd["value"], ss.threshold, band):
            continue
        alert = write_alert(ss.llm, rd["place"], rd["value"], rd["index"], ss.profile, ss.threshold, rd["pm25"])
        ss.alert_state.mark(rd["key"], rd["value"], band)
        pushed = bool(ss.push and telegram_configured() and send_telegram(format_alert(alert))[0])
        entry = {**alert, "place": rd["place"], "value": rd["value"], "index": rd["index"],
                 "at": state.now_label(), "pushed": pushed}
        ss.alert_log.insert(0, entry)
        new.append(entry)
    ss.last_check = state.now_label()
    ss.checks += 1
    return readings, new


@st.fragment(run_every=ss.check_every * 60 if ss.auto_check else None)
def watcher():
    readings, new = check_watchlist()
    over = [r for r in readings if r["value"] is not None and r["value"] > ss.threshold]
    sources = {r.get("source") for r in readings}
    n = len(readings)
    items = [
        ("warn" if over else "on", f"{len(over)} of {n} places" if over else f"All {n} places",
         "are above your limit." if over else "are within your limit."),
        ("on" if ss.auto_check else "off", "Last checked", f"{ss.last_check}." if ss.last_check else "not yet."),
        ("on" if ss.llm.live else "off", "AI", "Nemotron is on." if ss.llm.live else "is off (no API key)."),
        ("on" if ss.push and telegram_configured() else "off", "Phone alerts",
         "on." if ss.push and telegram_configured() else "off."),
        ("warn" if "sample" in sources else "on", "Data",
         "sample, live feed unreachable." if "sample" in sources else "live from NEA and CAMS."),
    ]
    st.html(ui.status(items))
    if new:
        if len(new) == 1:
            body = f"**{new[0]['title']}**\n\n{new[0]['message']}"
        else:
            body = f"**{len(new)} places are above your limit**\n\nOpen Alerts to see them."
        if ss.get("full_run"):
            st.toast(body, icon=":material/notifications_active:")
        else:  # a timed check on its own: redraw the page so the new alerts show up everywhere
            ss.pending_toasts.append({"body": body, "icon": ":material/notifications_active:"})
            st.rerun(scope="app")


with st.sidebar:
    st.html('<p class="ph-side-tag">Haze is just a phase.</p>'
            '<p class="ph-side-sub">Get alerted when the air leaves the healthy range.</p>')
    st.slider("Alert me above", 50, 300, step=10, key="threshold",
              help="PSI in Singapore, US AQI everywhere else. Above 100 is outside the healthy range.")
    limit_band = band_for(ss.threshold, "psi")
    st.html(f'<p class="ph-note" style="margin-top:-.6rem">{ss.threshold} is in the {limit_band.label.lower()} range.</p>')
    st.selectbox("Who is this for?", list(PROFILES), key="profile",
                 help="Changes the advice on the Now page and the wording of alerts.")
    st.divider()
    watcher()
    st.button("Refresh readings", icon=":material/refresh:", on_click=st.cache_data.clear, width="stretch")

pages = {
    "now": st.Page(now.render, title="Now", icon=":material/wb_sunny:", url_path="now", default=True),
    "map": st.Page(map_page.render, title="Map", icon=":material/public:", url_path="map"),
    "plan": st.Page(plan.render, title="Plan", icon=":material/event_available:", url_path="plan"),
    "news": st.Page(news.render, title="News", icon=":material/newspaper:", url_path="news"),
    "ask": st.Page(ask.render, title="Ask", icon=":material/forum:", url_path="ask"),
    "alerts": st.Page(alerts.render, title="Alerts", icon=":material/notifications:", url_path="alerts"),
    "how": st.Page(how.render, title="How it works", icon=":material/hub:", url_path="how-it-works"),
}
state.PAGES.update(pages)
st.navigation(list(pages.values()), position="top").run()
ss.full_run = False
