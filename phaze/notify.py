"""Telegram push notifications and alert de-duplication.

Telegram is free and reaches your phone instantly:
1. Message @BotFather on Telegram, send /newbot, and copy the bot token.
2. Send any message to your new bot.
3. Open https://api.telegram.org/bot<TOKEN>/getUpdates and copy "chat":{"id": ...}.
4. Put both in .env as TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests


def telegram_configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def send_telegram(text: str, token: str | None = None, chat_id: str | None = None) -> tuple[bool, str]:
    token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "Telegram isn't set up. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env."
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=10,
        )
        if resp.ok and resp.json().get("ok"):
            return True, "Sent"
        return False, f"Telegram said: {resp.text[:200]}"
    except Exception as exc:
        return False, f"Couldn't reach Telegram: {exc}"


def format_alert(alert: dict) -> str:
    lines = [f"⚠️ {alert['title']}", "", alert["message"]]
    if alert.get("actions"):
        lines.append("")
        lines += [f"• {a}" for a in alert["actions"]]
    lines += ["", "— PHAZE"]
    return "\n".join(lines)


class AlertState:
    """Remembers when each place last alerted, so you get one alert per episode, not one every check.

    A place alerts when it first goes above the limit, then again only if it's still
    above after the cooldown, or if it gets noticeably worse (jumps a band).
    """

    def __init__(self, path: str | Path | None = None, cooldown_hours: float = 3.0):
        self.path = Path(path) if path else None
        self.cooldown = cooldown_hours * 3600
        self.state: dict = {}
        if self.path and self.path.exists():
            try:
                self.state = json.loads(self.path.read_text())
            except Exception:
                self.state = {}

    def should_alert(self, key: str, value: float, threshold: float, band: str, now: float | None = None) -> bool:
        now = now or time.time()
        prev = self.state.get(key)
        if value <= threshold:
            if prev:
                prev["active"] = False
            return False
        if not prev or not prev.get("active"):
            return True
        if band != prev.get("band"):
            return value > prev.get("value", 0)  # only re-alert if it got worse
        return now - prev.get("at", 0) >= self.cooldown

    def mark(self, key: str, value: float, band: str, now: float | None = None):
        self.state[key] = {"at": now or time.time(), "value": value, "band": band, "active": True}

    def save(self):
        if self.path:
            self.path.write_text(json.dumps(self.state, indent=2))
