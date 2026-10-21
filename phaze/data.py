"""Fetching air quality data.

- Singapore: official PSI from NEA via data.gov.sg (real-time API).
- Rest of the world: US AQI, PM2.5 and PM10 from the free Open-Meteo Air Quality API
  (CAMS model data). No API key needed for non-commercial use.

Every fetch falls back to bundled sample data if the network call fails, so the app
always runs. Results carry a "source" field ("live" or "sample") so the UI can say which.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests

SG_PSI_URL = "https://api-open.data.gov.sg/v2/real-time/api/psi"
OPEN_METEO_AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPEN_METEO_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"
TIMEOUT = 12
HEADERS = {"User-Agent": "PHAZE/0.1 (hackathon project)"}


def _key(name: str, country: str) -> str:
    return f"{name}, {country}"


# ---------------------------------------------------------------- Singapore PSI

def parse_sg_psi(payload: dict) -> dict:
    """Turn the data.gov.sg PSI payload into {timestamp, regions{name: {psi, pm25, lat, lon}}}."""
    data = payload.get("data") or {}
    items = data.get("items") or []
    if not items:
        raise ValueError("PSI payload has no items")
    item = items[-1]
    readings = item.get("readings") or {}
    psi = readings.get("psi_twenty_four_hourly") or {}
    pm25 = readings.get("pm25_twenty_four_hourly") or {}
    meta = {m["name"]: m.get("labelLocation", {}) for m in data.get("regionMetadata", [])}

    regions = {}
    for name in ["north", "south", "east", "west", "central"]:
        if name not in psi:
            continue
        loc = meta.get(name, {})
        regions[name] = {
            "psi": psi.get(name),
            "pm25": pm25.get(name),
            "lat": loc.get("latitude"),
            "lon": loc.get("longitude"),
        }
    if not regions:
        raise ValueError("PSI payload has no regional readings")
    return {"timestamp": item.get("timestamp") or item.get("updatedTimestamp"), "regions": regions}


def fetch_sg_psi() -> dict:
    headers = dict(HEADERS)
    if os.getenv("DATA_GOV_SG_API_KEY"):
        headers["x-api-key"] = os.environ["DATA_GOV_SG_API_KEY"]
    try:
        resp = requests.get(SG_PSI_URL, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        result = parse_sg_psi(resp.json())
        result["source"] = "live"
        return result
    except Exception as exc:  # network down, API change, rate limit
        result = parse_sg_psi(json.loads((SAMPLE_DIR / "sg_psi.json").read_text()))
        result["source"] = "sample"
        result["error"] = str(exc)
        return result


def sg_overall(psi: dict) -> int | None:
    values = [r["psi"] for r in psi["regions"].values() if r.get("psi") is not None]
    return max(values) if values else None


# ---------------------------------------------------------------- World AQI

def parse_open_meteo_current(payload, cities: list[dict]) -> list[dict]:
    """Open-Meteo returns a dict for one location and a list for several."""
    blocks = payload if isinstance(payload, list) else [payload]
    rows = []
    for city, block in zip(cities, blocks):
        cur = (block or {}).get("current") or {}
        rows.append({
            **city,
            "us_aqi": _num(cur.get("us_aqi")),
            "pm2_5": _num(cur.get("pm2_5")),
            "pm10": _num(cur.get("pm10")),
            "time": cur.get("time"),
        })
    return rows


def _num(value):
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else round(v, 1)


def fetch_world(cities: list[dict], chunk_size: int = 40) -> dict:
    rows: list[dict] = []
    try:
        for i in range(0, len(cities), chunk_size):
            chunk = cities[i:i + chunk_size]
            params = {
                "latitude": ",".join(str(c["lat"]) for c in chunk),
                "longitude": ",".join(str(c["lon"]) for c in chunk),
                "current": "us_aqi,pm2_5,pm10",
                "timezone": "auto",
            }
            resp = requests.get(OPEN_METEO_AQ_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            rows.extend(parse_open_meteo_current(resp.json(), chunk))
        return {"rows": rows, "source": "live"}
    except Exception as exc:
        return {"rows": sample_world(cities), "source": "sample", "error": str(exc)}


def sample_world(cities: list[dict]) -> list[dict]:
    sample = json.loads((SAMPLE_DIR / "world_aqi.json").read_text())
    readings = sample["readings"]
    rows = []
    for c in cities:
        r = readings.get(_key(c["name"], c["country"]))
        if r is None:  # a custom city we have no sample for: make a stable placeholder value
            seed = abs(hash(_key(c["name"], c["country"]))) % 90
            r = {"us_aqi": 30 + seed, "pm2_5": round((30 + seed) / 3.2, 1), "pm10": round((30 + seed) / 2, 1)}
        rows.append({**c, **r, "time": sample["time"]})
    return rows


# ---------------------------------------------------------------- Forecast

def parse_open_meteo_hourly(payload: dict, hours: int) -> dict:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    aqi = [_num(v) for v in hourly.get("us_aqi") or []]
    pm25 = [_num(v) for v in hourly.get("pm2_5") or []]
    # start from the current hour
    now = payload.get("current", {}).get("time")
    start = 0
    if now:
        now_hour = now[:13]
        for i, t in enumerate(times):
            if t[:13] >= now_hour:
                start = i
                break
    end = start + hours
    return {"times": times[start:end], "us_aqi": aqi[start:end], "pm2_5": pm25[start:end]}


def fetch_forecast(lat: float, lon: float, hours: int = 48) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "us_aqi,pm2_5",
        "current": "us_aqi",
        "forecast_days": 3,
        "timezone": "auto",
    }
    try:
        resp = requests.get(OPEN_METEO_AQ_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        result = parse_open_meteo_hourly(resp.json(), hours)
        if not result["times"]:
            raise ValueError("empty forecast")
        result["source"] = "live"
        return result
    except Exception as exc:
        result = sample_forecast(lat, lon, hours)
        result["error"] = str(exc)
        return result


def fetch_forecasts(cities: list[dict], hours: int = 48, current: dict | None = None) -> dict:
    """Forecasts for several places in one request. Returns {"Name, Country": forecast}.

    `current` ({"Name, Country": value}) only shapes the offline sample curves,
    so they start near today's reading.
    """
    out: dict = {}
    if not cities:
        return out
    current = current or {}
    params = {
        "latitude": ",".join(str(c["lat"]) for c in cities),
        "longitude": ",".join(str(c["lon"]) for c in cities),
        "hourly": "us_aqi,pm2_5",
        "current": "us_aqi",
        "forecast_days": 3,
        "timezone": ",".join(["auto"] * len(cities)),
    }
    try:
        resp = requests.get(OPEN_METEO_AQ_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        blocks = payload if isinstance(payload, list) else [payload]
        for city, block in zip(cities, blocks):
            key = _key(city["name"], city["country"])
            fc = parse_open_meteo_hourly(block or {}, hours)
            if fc["times"]:
                fc["source"] = "live"
            else:
                fc = sample_forecast(city["lat"], city["lon"], hours, current.get(key))
            out[key] = fc
    except Exception as exc:
        for city in cities:
            key = _key(city["name"], city["country"])
            out[key] = {**sample_forecast(city["lat"], city["lon"], hours, current.get(key)), "error": str(exc)}
    return out


def sample_forecast(lat: float, lon: float, hours: int = 48, base: float | None = None) -> dict:
    """A smooth, repeatable made-up curve so the forecast view works offline."""
    seed = abs(int(lat * 100 + lon * 10))
    if base is None:
        base = 60 + (seed % 90)
    slope = ((seed % 7) - 3) * 0.45  # some places get better, some worse
    start = datetime.now().replace(minute=0, second=0, microsecond=0)
    times, aqi, pm25 = [], [], []
    for h in range(hours):
        t = start + timedelta(hours=h)
        # haze tends to build overnight and ease in the afternoon
        daily = 0.18 * base * (math.cos((t.hour - 4) / 24 * 2 * math.pi) - math.cos((start.hour - 4) / 24 * 2 * math.pi))
        value = max(12, base + daily + slope * h)
        times.append(t.strftime("%Y-%m-%dT%H:%M"))
        aqi.append(round(value))
        pm25.append(round(value / 2.9, 1))
    return {"times": times, "us_aqi": aqi, "pm2_5": pm25, "source": "sample"}


# ---------------------------------------------------------------- Geocoding

def geocode(name: str, count: int = 5) -> list[dict]:
    """Look up a place name. Returns [] if nothing found or offline."""
    name = (name or "").strip()
    if not name:
        return []
    try:
        resp = requests.get(
            OPEN_METEO_GEO_URL,
            params={"name": name, "count": count, "language": "en", "format": "json"},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except Exception:
        return []
    out = []
    for r in results:
        out.append({
            "name": r.get("name"),
            "country": r.get("country") or r.get("country_code") or "",
            "lat": r.get("latitude"),
            "lon": r.get("longitude"),
            "region": "Custom",
            "admin": r.get("admin1") or "",
        })
    return out


# ---------------------------------------------------------------- Helpers

def windows_below(times: list[str], values: list, threshold: float, min_hours: int = 2) -> list[dict]:
    """Find stretches of consecutive hours at or under the threshold."""
    windows, start = [], None
    for i, v in enumerate(values + [None]):
        ok = v is not None and v <= threshold
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start >= min_hours:
                seg = values[start:i]
                windows.append({
                    "start": times[start],
                    "end": times[i - 1],
                    "hours": i - start,
                    "avg": round(sum(seg) / len(seg)),
                    "max": max(seg),
                })
            start = None
    return windows


def peak(times: list[str], values: list) -> dict | None:
    pairs = [(v, t) for t, v in zip(times, values) if v is not None]
    if not pairs:
        return None
    v, t = max(pairs)
    return {"time": t, "value": v}
