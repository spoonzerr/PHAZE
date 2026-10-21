"""PHAZE: track haze around the world and get alerted when air quality leaves the healthy range.

Run:  streamlit run app.py
"""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import pydeck as pdk
import streamlit as st
from dotenv import load_dotenv

from phaze.agents import ACTIVITIES, PROFILES, SAFETY_LINE, ask, haze_report, plan_outdoors, write_alert
from phaze.bands import AQI_BANDS, HEALTHY_LIMIT, PSI_BANDS, band_for, index_name
from phaze.cities import DEFAULT_CITIES, REGIONS, city_key, find_city
from phaze.data import fetch_forecast, fetch_sg_psi, fetch_world, geocode, sg_overall
from phaze.llm import LLM
from phaze.notify import AlertState, format_alert, send_telegram, telegram_configured

load_dotenv()
st.set_page_config(page_title="PHAZE", page_icon="🌫️", layout="wide")

# ------------------------------------------------------------------ session state

ss = st.session_state
ss.setdefault("llm", LLM())
ss.setdefault("custom_cities", [])
ss.setdefault("watchlist", ["Singapore, Singapore", "Kuala Lumpur, Malaysia", "Jakarta, Indonesia"])
ss.setdefault("alert_log", [])
ss.setdefault("alert_state", AlertState(cooldown_hours=3))
ss.setdefault("chat", [])
ss.setdefault("geo_results", [])
llm: LLM = ss.llm


def all_cities() -> list[dict]:
    return DEFAULT_CITIES + ss.custom_cities


# ------------------------------------------------------------------ cached data

@st.cache_data(ttl=600, show_spinner=False)
def get_sg():
    return fetch_sg_psi()


@st.cache_data(ttl=600, show_spinner=False)
def get_world(cities_json: str):
    return fetch_world(json.loads(cities_json))


@st.cache_data(ttl=1800, show_spinner=False)
def get_forecast(lat: float, lon: float):
    return fetch_forecast(lat, lon, hours=48)


def world_rows() -> tuple[list[dict], str]:
    res = get_world(json.dumps(all_cities()))
    return res["rows"], res["source"]


def fmt_ts(ts: str | None) -> str:
    if not ts:
        return "unknown time"
    try:
        return datetime.fromisoformat(ts).strftime("%d %b %Y, %I:%M %p").replace(", 0", ", ")
    except ValueError:
        return ts


def band_chip(value, index="aqi") -> str:
    b = band_for(value, index)
    v = "–" if value is None else round(value)
    return (f"<span style='background:{b.color_hex}22;color:{b.color_hex};border:1px solid {b.color_hex}66;"
            f"padding:2px 8px;border-radius:999px;font-size:0.85em;white-space:nowrap'>{v} · {b.label}</span>")


def source_note(source: str, what: str):
    if source != "live":
        st.caption(f"⚠️ Showing sample {what} data because the live source couldn't be reached.")


# ------------------------------------------------------------------ sidebar

with st.sidebar:
    st.title("🌫️ PHAZE")
    st.caption("Haze tracking and alerts, powered by NVIDIA Nemotron on Nebius Token Factory.")

    ss.threshold = st.slider(
        "Alert me above", 50, 300, int(ss.get("threshold", HEALTHY_LIMIT)), step=10,
        help="PSI in Singapore, US AQI elsewhere. Above 100 is outside the healthy range.",
    )
    ss.profile = st.selectbox("Who are the alerts for?", list(PROFILES),
                              index=list(PROFILES).index(ss.get("profile", "General public")))

    st.divider()
    if llm.live:
        st.success("AI: Nemotron live", icon="✅")
    else:
        st.info("AI: demo mode. Add NEBIUS_API_KEY to .env to switch on Nemotron.", icon="ℹ️")
    st.caption(("✅" if telegram_configured() else "➖") + " Telegram alerts")
    if st.button("Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Data: NEA via data.gov.sg (Singapore PSI); Open-Meteo and CAMS (world AQI). "
               "Updates every 10 minutes.")

threshold = ss.threshold
profile = ss.profile

tab_map, tab_sg, tab_alerts, tab_outlook, tab_news, tab_ask, tab_hood = st.tabs(
    ["🌍 World map", "🇸🇬 Singapore PSI", "🔔 My alerts", "📈 48-hour outlook", "📰 Haze news", "💬 Ask", "⚙️ Under the hood"]
)

# ------------------------------------------------------------------ world map

with tab_map:
    with st.spinner("Loading air quality around the world..."):
        rows, src = world_rows()
    source_note(src, "world")
    df = pd.DataFrame(rows)
    df["band"] = df["us_aqi"].apply(lambda v: band_for(v).label)
    df["color"] = df["us_aqi"].apply(lambda v: list(band_for(v).rgb) + [210])
    df["radius"] = df["us_aqi"].fillna(20).clip(lower=20) * 900
    df["place"] = df["name"] + ", " + df["country"]

    over = df[df["us_aqi"] > threshold]
    worst = df.sort_values("us_aqi", ascending=False).iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Places tracked", len(df))
    c2.metric(f"Above your limit ({threshold})", len(over))
    c3.metric("Worst right now", f"{worst['name']}", f"US AQI {round(worst['us_aqi'])}", delta_color="off",
              delta_arrow="off")

    layer = pdk.Layer(
        "ScatterplotLayer", data=df, get_position="[lon, lat]", get_fill_color="color",
        get_radius="radius", radius_min_pixels=5, radius_max_pixels=40, pickable=True,
        stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=1,
    )
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(latitude=12, longitude=100, zoom=1.6),
        tooltip={"text": "{place}\nUS AQI {us_aqi} ({band})\nPM2.5 {pm2_5} µg/m³"},
    ), width="stretch")

    legend = " ".join(f"<span style='color:{b.color_hex}'>●</span> {b.label} (≤{int(b.upper) if b.upper != float('inf') else '301+'})"
                      for b in AQI_BANDS)
    st.markdown(f"<div style='font-size:0.85em'>{legend}</div>", unsafe_allow_html=True)

    st.subheader("Worst air right now")
    table = df.sort_values("us_aqi", ascending=False)[["place", "region", "us_aqi", "band", "pm2_5", "pm10"]]
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "place": "Place", "region": "Region", "band": "Level",
            "us_aqi": st.column_config.ProgressColumn("US AQI", min_value=0, max_value=300, format="%d"),
            "pm2_5": st.column_config.NumberColumn("PM2.5 (µg/m³)", format="%.1f"),
            "pm10": st.column_config.NumberColumn("PM10 (µg/m³)", format="%.1f"),
        },
    )

# ------------------------------------------------------------------ singapore

with tab_sg:
    psi = get_sg()
    source_note(psi["source"], "Singapore")
    overall = sg_overall(psi)
    b = band_for(overall, "psi")
    st.markdown(f"### 24-hour PSI: {band_chip(overall, 'psi')}", unsafe_allow_html=True)
    st.caption(f"Official NEA reading for {fmt_ts(psi['timestamp'])}. Overall = highest region.")
    if overall is not None and overall > HEALTHY_LIMIT:
        st.warning(f"**{b.label}.** {b.advice}")
    else:
        st.success(f"**{b.label}.** {b.advice}")

    cols = st.columns(5)
    for col, (region, r) in zip(cols, psi["regions"].items()):
        rb = band_for(r["psi"], "psi")
        col.metric(region.title(), r["psi"], rb.label, delta_color="off")
        col.caption(f"PM2.5: {r['pm25']} µg/m³")

    chart = pd.DataFrame({"Region": [k.title() for k in psi["regions"]],
                          "PSI": [r["psi"] for r in psi["regions"].values()]}).set_index("Region")
    st.bar_chart(chart, height=260, color="#e8590c" if overall and overall > 100 else "#2f9e44")

    with st.expander("What do the PSI levels mean?"):
        bands_rows = []
        for prev, bd in zip([None] + [x.upper for x in PSI_BANDS[:-1]], PSI_BANDS):
            lo = int(prev) + 1 if prev else 0
            rng = f"{lo}+" if bd.upper == float("inf") else f"{lo}–{int(bd.upper)}"
            bands_rows.append({"PSI": rng, "Level": bd.label, "What to do": bd.advice})
        st.table(pd.DataFrame(bands_rows).set_index("PSI"))
        st.caption(SAFETY_LINE)

# ------------------------------------------------------------------ alerts

with tab_alerts:
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Your watchlist")
        options = [city_key(c) for c in all_cities()]
        ss.watchlist = st.multiselect("Places to watch", options,
                                      default=[w for w in ss.watchlist if w in options])

        with st.expander("Add any city in the world"):
            q = st.text_input("City name", placeholder="Pekanbaru")
            if st.button("Search") and q:
                ss.geo_results = geocode(q)
                if not ss.geo_results:
                    st.error("Couldn't find that place, or the lookup service is offline. Try another spelling.")
            if ss.geo_results:
                labels = [f"{g['name']}, {g['admin'] + ', ' if g['admin'] else ''}{g['country']}" for g in ss.geo_results]
                pick = st.selectbox("Pick the right one", range(len(labels)), format_func=lambda i: labels[i])
                if st.button("Add to watchlist"):
                    g = ss.geo_results[pick]
                    if city_key(g) not in options:
                        ss.custom_cities.append(g)
                    ss.watchlist = list(dict.fromkeys(ss.watchlist + [city_key(g)]))
                    ss.geo_results = []
                    st.cache_data.clear()
                    st.rerun()

    with right:
        st.subheader("Notifications")
        auto = st.toggle("Check automatically", value=True)
        every = st.select_slider("Check every", options=[1, 5, 10, 15, 30], value=5, format_func=lambda m: f"{m} min")
        push = st.toggle("Also send to Telegram", value=telegram_configured(), disabled=not telegram_configured(),
                         help="Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env. See README.")
        if st.button("Send test notification", disabled=not telegram_configured()):
            ok, msg = send_telegram("✅ PHAZE test: notifications are working.")
            (st.success if ok else st.error)(msg)
        watch_json = json.dumps({
            "threshold": threshold, "profile": profile, "cities": ss.watchlist,
            "custom_cities": [c for c in ss.custom_cities if city_key(c) in ss.watchlist],
        }, indent=2)
        st.download_button("Download watchlist.json", watch_json, "watchlist.json", "application/json",
                           help="Use it with notifier.py to get alerts when the app is closed.")

    def current_readings() -> list[dict]:
        """Readings for everything on the watchlist. Singapore uses official PSI by region."""
        out = []
        watch = set(ss.watchlist)
        if "Singapore, Singapore" in watch:
            psi = get_sg()
            for region, r in psi["regions"].items():
                out.append({"key": f"sg-{region}", "place": f"Singapore ({region.title()})", "value": r["psi"],
                            "index": "psi", "pm25": r["pm25"], "source": psi["source"]})
        rows, src = world_rows()
        for r in rows:
            k = city_key(r)
            if k in watch and k != "Singapore, Singapore":
                out.append({"key": k, "place": k, "value": r["us_aqi"], "index": "aqi", "pm25": r["pm2_5"], "source": src})
        return out

    @st.fragment(run_every=every * 60 if auto else None)
    def live_alerts():
        readings = current_readings()
        new = 0
        for rd in readings:
            if rd["value"] is None:
                continue
            band = band_for(rd["value"], rd["index"]).label
            if ss.alert_state.should_alert(rd["key"], rd["value"], threshold, band):
                alert = write_alert(llm, rd["place"], rd["value"], rd["index"], profile, threshold, rd["pm25"])
                ss.alert_state.mark(rd["key"], rd["value"], band)
                ss.alert_log.insert(0, {**alert, "place": rd["place"], "value": rd["value"],
                                        "index": rd["index"], "at": datetime.now().strftime("%I:%M %p").lstrip("0")})
                st.toast(f"**{alert['title']}**\n\n{alert['message']}", icon="⚠️")
                if push:
                    send_telegram(format_alert(alert))
                new += 1

        st.caption(f"Last checked {datetime.now().strftime('%I:%M:%S %p').lstrip('0')}"
                   + (f" · next check in {every} min" if auto else " · automatic checks off"))
        if not readings:
            st.info("Add some places to your watchlist to start.")
        for rd in sorted(readings, key=lambda r: -(r["value"] or 0)):
            over = rd["value"] is not None and rd["value"] > threshold
            st.markdown(
                f"{'🔴' if over else '🟢'} **{rd['place']}** &nbsp; {index_name(rd['index'])} "
                f"{band_chip(rd['value'], rd['index'])}", unsafe_allow_html=True)

        st.subheader("Alert history")
        if not ss.alert_log:
            st.caption("No alerts yet. You'll get one the moment a place on your watchlist goes above "
                       f"{threshold}.")
        for a in ss.alert_log[:20]:
            with st.container(border=True):
                st.markdown(f"**{a['title']}** · {a['at']}")
                st.write(a["message"])
                if a.get("actions"):
                    st.markdown("\n".join(f"- {x}" for x in a["actions"]))
                st.caption(("Written by Nemotron Nano" if a["by"] == "nano" else "Rule-based message") + f" · {SAFETY_LINE}")

    with left:
        st.divider()
        live_alerts()
        if st.button("Check now"):
            st.rerun()

# ------------------------------------------------------------------ outlook

with tab_outlook:
    st.subheader("Plan around the haze")
    options = [city_key(c) for c in all_cities()]
    default_place = ss.watchlist[0] if ss.watchlist else options[0]
    c1, c2 = st.columns(2)
    place_key = c1.selectbox("Place", options, index=options.index(default_place) if default_place in options else 0)
    activity = c2.selectbox("What are you planning?", ACTIVITIES)
    city = find_city(place_key, all_cities()) or DEFAULT_CITIES[0]

    fc = get_forecast(city["lat"], city["lon"])
    source_note(fc["source"], "forecast")
    if fc["times"]:
        chart_df = pd.DataFrame({
            "Time": pd.to_datetime(fc["times"]),
            "US AQI forecast": fc["us_aqi"],
            "Your limit": [threshold] * len(fc["times"]),
        }).set_index("Time")
        st.line_chart(chart_df, height=300, color=["#e8590c", "#868e96"])
        st.caption("Forecast from the CAMS model via Open-Meteo. US AQI, hourly.")

        if st.button("Find my best times ✨", type="primary"):
            with st.spinner("Nemotron Super is reading the forecast..."):
                ss.plan = {"place": place_key, "activity": activity,
                           **plan_outdoors(llm, place_key, fc, profile, activity, threshold)}
        plan = ss.get("plan")
        if plan and plan["place"] == place_key and plan["activity"] == activity:
            with st.container(border=True):
                st.write(plan["summary"])
                for w in plan["windows"]:
                    st.markdown(f"- **{w['when']}**: {w['why']}")
                if plan.get("tip"):
                    st.info(plan["tip"], icon="💡")
                st.caption(("Planned by Nemotron Super" if plan["by"] == "super" else "Rule-based plan (demo mode)")
                           + f" · {SAFETY_LINE}")

# ------------------------------------------------------------------ news

with tab_news:
    st.subheader("What's causing the haze?")
    st.caption("Searches the latest news with Tavily, then Nemotron Super summarises it with citations.")
    area = st.selectbox("Area", ["Singapore and Malaysia", "Indonesia (Sumatra and Kalimantan)", "Thailand",
                                 "Northern India and Pakistan", "Southeast Asia"] + [r for r in REGIONS if r != "Southeast Asia"])
    custom_area = st.text_input("Or type any place", placeholder="Chiang Mai")
    target = custom_area.strip() or area
    if st.button("Get the latest", type="primary"):
        rows, _ = world_rows()
        worst = sorted([r for r in rows if r["us_aqi"]], key=lambda r: -r["us_aqi"])[:5]
        note = "Current worst readings tracked by PHAZE: " + ", ".join(f"{r['name']} {round(r['us_aqi'])}" for r in worst)
        with st.spinner("Searching and summarising..."):
            ss.report = {"area": target, **haze_report(llm, target, note)}
    rep = ss.get("report")
    if rep and rep["area"] == target:
        with st.container(border=True):
            st.write(rep["summary"])
            if rep["causes"]:
                st.markdown("**Main causes**\n" + "\n".join(f"- {c}" for c in rep["causes"]))
            if rep["outlook"]:
                st.markdown(f"**Outlook:** {rep['outlook']}")
            if rep["sources"]:
                st.markdown("**Sources**\n" + "\n".join(f"{i + 1}. [{s['title']}]({s['url']})"
                                                        for i, s in enumerate(rep["sources"])))
            st.caption("Summarised by Nemotron Super" if rep["by"] == "super" else rep["by"])

# ------------------------------------------------------------------ ask

def readings_context() -> str:
    psi = get_sg()
    rows, _ = world_rows()
    lines = [f"Singapore 24h PSI by region ({fmt_ts(psi['timestamp'])}): "
             + ", ".join(f"{k} {v['psi']}" for k, v in psi["regions"].items())]
    top = sorted([r for r in rows if r["us_aqi"] is not None], key=lambda r: -r["us_aqi"])
    lines.append("US AQI now: " + ", ".join(f"{r['name']} {round(r['us_aqi'])}" for r in top))
    lines.append(f"User's alert limit: {threshold}. User profile: {profile}. Watchlist: {', '.join(ss.watchlist)}")
    return "\n".join(lines)


with tab_ask:
    st.subheader("Ask PHAZE")
    st.caption("Nemotron Nano reads your question first. Simple questions stay on Nano; "
               "harder ones go to Nemotron Super, with a web search when it needs fresh news.")
    for m in ss.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("meta"):
                st.caption(m["meta"])
    examples = ["Is it safe to jog in Singapore today?", "What's the difference between PSI and PM2.5?",
                "Why does haze get worse in September and October?"]
    picked = None
    if not ss.chat:
        cols = st.columns(len(examples))
        for col, ex in zip(cols, examples):
            if col.button(ex, width="stretch"):
                picked = ex
    question = st.chat_input("Ask about haze, air quality or your plans") or picked
    if question:
        ss.chat.append({"role": "user", "content": question})
        with st.spinner("Thinking..."):
            res = ask(llm, question, readings_context(),
                      history=[{"role": m["role"], "content": m["content"]} for m in ss.chat[:-1]])
        answer = res["answer"]
        if res["sources"]:
            answer += "\n\n" + "\n".join(f"[{i + 1}] [{s['title']}]({s['url']})" for i, s in enumerate(res["sources"]))
        meta = {"nano": "Answered by Nemotron Nano (easy question)",
                "super": "Answered by Nemotron Super (harder question)",
                "demo": "Demo mode"}[res["tier"]]
        if res["route"].get("needs_search"):
            meta += " · searched the web with Tavily"
        ss.chat.append({"role": "assistant", "content": answer, "meta": meta})
        st.rerun()

# ------------------------------------------------------------------ under the hood

with tab_hood:
    st.subheader("How PHAZE uses Nemotron")
    st.markdown(
        "| Agent | Model | Why this model |\n|---|---|---|\n"
        "| Alert writer | Nemotron 3 Nano | Runs on every alert, so it needs to be fast and cheap |\n"
        "| Question router | Nemotron 3 Nano | A tiny classification job: easy or hard, search or not |\n"
        "| Ask (easy) | Nemotron 3 Nano | Definitions and simple facts don't need a big model |\n"
        "| Ask (hard), Outdoor planner | Nemotron 3 Super | Multi-step reasoning over a 48-hour forecast |\n"
        "| Haze reporter | Nemotron 3 Super + Tavily | Reading several news articles and citing them accurately |"
    )
    st.caption(f"Models: `{llm.nano_model}` and `{llm.super_model}` via {llm.base_url}")

    s = llm.summary()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nano calls", s["nano"]["calls"])
    c2.metric("Super calls", s["super"]["calls"])
    c3.metric("Handled by Nano", f"{round(s['nano_share'] * 100)}%" if s["nano_share"] is not None else "–")
    total_tokens = s["nano"]["tokens"] + s["super"]["tokens"]
    c4.metric("Tokens this session", f"{total_tokens:,}")

    stats = pd.DataFrame([
        {"Tier": t.title(), "Model": s[t]["model"], "Calls": s[t]["calls"], "Tokens": s[t]["tokens"],
         "Avg latency (s)": s[t]["avg_latency_s"],
         "Est. cost (USD)": round(s[t]["cost_usd"], 5) if s[t]["priced"] else None}
        for t in ("nano", "super")
    ])
    st.dataframe(stats, hide_index=True, width="stretch")
    if not s["super"]["priced"]:
        st.caption("Set SUPER_PRICE_IN and SUPER_PRICE_OUT in .env (USD per 1M tokens, from your Token Factory "
                   "dashboard) to see Super's cost.")

    if llm.records:
        st.markdown("**Call log**")
        st.dataframe(pd.DataFrame([{
            "Agent": r.agent, "Model": r.model, "Tokens in": r.prompt_tokens, "Tokens out": r.completion_tokens,
            "Latency (s)": round(r.latency_s, 2), "OK": "✅" if r.ok else f"❌ {r.error[:60]}",
        } for r in reversed(llm.records)]), hide_index=True, width="stretch")
    elif not llm.live:
        st.info("Demo mode: no model calls yet. Add NEBIUS_API_KEY to .env and restart to use Nemotron.")
