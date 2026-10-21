"""Session state and cached data shared by every page of the Streamlit app."""

from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from .bands import band_for
from .cities import DEFAULT_CITIES, city_key, find_city
from .data import fetch_forecasts, fetch_sg_psi, fetch_world
from .llm import LLM
from .notify import AlertState
from .watch import SINGAPORE, watch_readings

DEFAULT_WATCHLIST = [SINGAPORE, "Kuala Lumpur, Malaysia", "Jakarta, Indonesia"]
PAGES: dict = {}  # filled in by app.py so pages can link to each other


def init():
    ss = st.session_state
    ss.setdefault("llm", LLM())
    ss.setdefault("custom_cities", [])
    ss.setdefault("watchlist", list(DEFAULT_WATCHLIST))
    ss.setdefault("alert_log", [])
    ss.setdefault("alert_state", AlertState(cooldown_hours=3))
    ss.setdefault("chat", [])
    ss.setdefault("geo_results", [])
    ss.setdefault("threshold", 100)
    ss.setdefault("profile", "General public")
    ss.setdefault("home", ss.watchlist[0] if ss.watchlist else SINGAPORE)
    ss.setdefault("auto_check", True)
    ss.setdefault("check_every", 5)
    ss.setdefault("push", False)
    ss.setdefault("pending_toasts", [])
    ss.setdefault("last_check", None)
    ss.setdefault("checks", 0)


def all_cities() -> list[dict]:
    return DEFAULT_CITIES + st.session_state.custom_cities


def city(key: str) -> dict:
    return find_city(key, all_cities()) or DEFAULT_CITIES[0]


def short(key: str) -> str:
    return key.split(",")[0]


# ------------------------------------------------------------------ cached fetches

@st.cache_data(ttl=600, show_spinner=False)
def sg() -> dict:
    return fetch_sg_psi()


@st.cache_data(ttl=600, show_spinner=False)
def _world(cities_json: str) -> dict:
    return fetch_world(json.loads(cities_json))


def world() -> tuple[list[dict], str]:
    res = _world(json.dumps(all_cities()))
    return res["rows"], res["source"]


@st.cache_data(ttl=1800, show_spinner=False)
def _forecasts(cities_json: str, current_json: str) -> dict:
    return fetch_forecasts(json.loads(cities_json), 48, json.loads(current_json))


def forecasts(keys: list[str]) -> dict:
    """48-hour US AQI forecasts for some places, fetched together in one request."""
    cities = [city(k) for k in keys]
    rows, _ = world()
    current = {city_key(r): r["us_aqi"] for r in rows}
    return _forecasts(json.dumps(cities), json.dumps({city_key(c): current.get(city_key(c)) for c in cities}))


def readings() -> list[dict]:
    rows, src = world()
    for r in rows:
        r.setdefault("source", src)
    psi = sg() if SINGAPORE in st.session_state.watchlist else None
    return watch_readings(st.session_state.watchlist, psi, rows)


def reading_for(key: str) -> dict:
    """The reading for any place, watched or not."""
    rows, src = world()
    psi = sg() if key == SINGAPORE else None
    for r in rows:
        r.setdefault("source", src)
    found = watch_readings([key], psi, rows)
    if found:
        return found[0]
    c = city(key)
    return {"key": key, "name": c["name"], "country": c["country"], "place": key, "value": None, "index": "aqi",
            "pm25": None, "region": None, "source": src, "time": None}


def now_label() -> str:
    t = datetime.now()
    return f"{t.strftime('%I').lstrip('0') or '12'}:{t.strftime('%M')} {t.strftime('%p')}"


def band_label(value, index) -> str:
    return band_for(value, index).label
