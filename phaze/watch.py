"""What's on the watchlist right now, used by both the app and the background notifier."""

from __future__ import annotations

from .cities import city_key
from .data import sg_overall

SINGAPORE = "Singapore, Singapore"


def worst_region(psi: dict) -> tuple[str | None, dict]:
    regions = {k: v for k, v in psi.get("regions", {}).items() if v.get("psi") is not None}
    if not regions:
        return None, {}
    name = max(regions, key=lambda k: regions[k]["psi"])
    return name, regions[name]


def best_region(psi: dict) -> tuple[str | None, dict]:
    regions = {k: v for k, v in psi.get("regions", {}).items() if v.get("psi") is not None}
    if not regions:
        return None, {}
    name = min(regions, key=lambda k: regions[k]["psi"])
    return name, regions[name]


def watch_readings(watchlist: list[str], psi: dict | None, world_rows: list[dict]) -> list[dict]:
    """One reading per watched place, in watchlist order.

    Singapore uses the official NEA PSI and takes the worst of its five regions;
    everywhere else uses US AQI.
    """
    by_key = {city_key(r): r for r in world_rows}
    out = []
    for key in watchlist:
        if key == SINGAPORE and psi:
            region, r = worst_region(psi)
            out.append({
                "key": key, "name": "Singapore", "country": "Singapore",
                "place": f"Singapore ({region})" if region else "Singapore",
                "value": sg_overall(psi), "index": "psi", "pm25": r.get("pm25"),
                "region": region, "source": psi.get("source"), "time": psi.get("timestamp"),
            })
        elif key in by_key:
            r = by_key[key]
            out.append({
                "key": key, "name": r["name"], "country": r["country"], "place": key,
                "value": r.get("us_aqi"), "index": "aqi", "pm25": r.get("pm2_5"),
                "region": None, "source": r.get("source"), "time": r.get("time"),
            })
    return out
