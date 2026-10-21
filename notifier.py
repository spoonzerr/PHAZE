"""Background haze checker: run on a schedule to get Telegram alerts even when the app is closed.

Usage:
    python notifier.py                 # check once using watchlist.json
    python notifier.py --loop 15       # check every 15 minutes (keep a terminal open)
    python notifier.py --dry-run       # print alerts instead of sending them

Schedule it with GitHub Actions (see .github/workflows/haze-alerts.yml) or as a
Nebius Serverless Job. Download your watchlist.json from the app's Alerts tab.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from phaze.agents import write_alert
from phaze.bands import band_for
from phaze.cities import DEFAULT_CITIES, city_key
from phaze.data import fetch_sg_psi, fetch_world
from phaze.llm import LLM
from phaze.notify import AlertState, format_alert, send_telegram

ROOT = Path(__file__).resolve().parent
DEFAULT_WATCHLIST = {
    "threshold": 100,
    "profile": "General public",
    "cities": ["Singapore, Singapore", "Kuala Lumpur, Malaysia", "Jakarta, Indonesia"],
    "custom_cities": [],
}


def load_watchlist(path: Path) -> dict:
    if path.exists():
        return {**DEFAULT_WATCHLIST, **json.loads(path.read_text())}
    return DEFAULT_WATCHLIST


def check_once(watchlist: dict, state: AlertState, llm: LLM, dry_run: bool = False) -> list[dict]:
    threshold = float(watchlist["threshold"])
    profile = watchlist["profile"]
    pool = DEFAULT_CITIES + watchlist.get("custom_cities", [])
    cities = [c for c in pool if city_key(c) in watchlist["cities"]]

    readings = []  # (key, place, value, index, pm25)
    if "Singapore, Singapore" in watchlist["cities"]:
        psi = fetch_sg_psi()
        for region, r in psi["regions"].items():
            if r["psi"] is not None:
                readings.append((f"sg-{region}", f"Singapore ({region.title()})", r["psi"], "psi", r["pm25"]))
        cities = [c for c in cities if city_key(c) != "Singapore, Singapore"]
    if cities:
        world = fetch_world(cities)
        for row in world["rows"]:
            if row["us_aqi"] is not None:
                readings.append((city_key(row), city_key(row), row["us_aqi"], "aqi", row["pm2_5"]))

    sent = []
    for key, place, value, index, pm25 in readings:
        band = band_for(value, index).label
        if not state.should_alert(key, value, threshold, band):
            continue
        alert = write_alert(llm, place, value, index, profile, threshold, pm25)
        text = format_alert(alert)
        if dry_run:
            print(text, "\n")
            ok, msg = True, "dry run"
        else:
            ok, msg = send_telegram(text)
            print(f"{place}: {msg}")
        if ok:
            state.mark(key, value, band)
            sent.append({"place": place, "value": value, **alert})
    state.save()
    if not sent:
        print("No new alerts. Everything on your watchlist is within your limit, or already alerted.")
    return sent


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="PHAZE background alerts")
    parser.add_argument("--watchlist", default=str(ROOT / "watchlist.json"))
    parser.add_argument("--state", default=str(ROOT / ".alert_state.json"))
    parser.add_argument("--cooldown", type=float, default=3.0, help="hours before re-alerting the same place")
    parser.add_argument("--loop", type=float, default=0, help="minutes between checks (0 = run once)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    watchlist = load_watchlist(Path(args.watchlist))
    state = AlertState(args.state, cooldown_hours=args.cooldown)
    llm = LLM()
    print(f"Watching {len(watchlist['cities'])} places, limit {watchlist['threshold']}, "
          f"AI {'on (Nemotron via Token Factory)' if llm.live else 'off (demo mode)'}")
    while True:
        check_once(watchlist, state, llm, dry_run=args.dry_run)
        if not args.loop:
            break
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    main()
