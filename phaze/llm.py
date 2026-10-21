"""Nemotron on Nebius Token Factory, with simple model routing and usage tracking.

Two tiers:
- "nano"  -> Nemotron 3 Nano: fast and cheap. Used for short, frequent jobs
             (alert messages, classifying questions, quick answers).
- "super" -> Nemotron 3 Super: stronger reasoning. Used for planning and for
             summarising web research.

Token Factory speaks the OpenAI API, so we use the official `openai` client
pointed at the Token Factory base URL.

If NEBIUS_API_KEY isn't set, the app runs in demo mode: agents fall back to
rule-based text so the UI still works, and the usage panel says so.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
DEFAULT_NANO_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
DEFAULT_SUPER_MODEL = "nvidia/nemotron-3-super-120b-a12b"

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class CallRecord:
    agent: str
    tier: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    ok: bool = True
    error: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLM:
    api_key: str | None = None
    base_url: str | None = None
    nano_model: str | None = None
    super_model: str | None = None
    records: list[CallRecord] = field(default_factory=list)

    def __post_init__(self):
        self.api_key = self.api_key or os.getenv("NEBIUS_API_KEY") or None
        self.base_url = self.base_url or os.getenv("NEBIUS_BASE_URL") or DEFAULT_BASE_URL
        self.nano_model = self.nano_model or os.getenv("NEMOTRON_NANO_MODEL") or DEFAULT_NANO_MODEL
        self.super_model = self.super_model or os.getenv("NEMOTRON_SUPER_MODEL") or DEFAULT_SUPER_MODEL
        # USD per 1M tokens, used only for the cost estimate in the usage panel
        self.prices = {
            "nano": (_float_env("NANO_PRICE_IN", 0.06), _float_env("NANO_PRICE_OUT", 0.24)),
            "super": (_float_env("SUPER_PRICE_IN", 0.0), _float_env("SUPER_PRICE_OUT", 0.0)),
        }
        self._client = None
        if self.api_key:
            from openai import OpenAI

            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=60, max_retries=1)

    @property
    def live(self) -> bool:
        return self._client is not None

    def model_for(self, tier: str) -> str:
        return self.super_model if tier == "super" else self.nano_model

    def chat(
        self,
        messages: list[dict],
        tier: str = "nano",
        agent: str = "",
        max_tokens: int = 700,
        temperature: float = 0.3,
    ) -> str | None:
        """Send a chat request. Returns the reply text, or None in demo mode or on error."""
        if not self.live:
            return None
        model = self.model_for(tier)
        started = time.perf_counter()
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            latency = time.perf_counter() - started
            usage = getattr(resp, "usage", None)
            self.records.append(CallRecord(
                agent=agent,
                tier=tier,
                model=model,
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                latency_s=latency,
            ))
            text = resp.choices[0].message.content or ""
            return clean(text)
        except Exception as exc:
            self.records.append(CallRecord(agent, tier, model, 0, 0, time.perf_counter() - started, False, str(exc)[:300]))
            return None

    def chat_json(self, messages: list[dict], **kwargs) -> dict | None:
        text = self.chat(messages, **kwargs)
        return extract_json(text) if text else None

    # ------------------------------------------------------------ usage stats

    def cost_usd(self, rec: CallRecord) -> float:
        p_in, p_out = self.prices.get(rec.tier, (0.0, 0.0))
        return (rec.prompt_tokens * p_in + rec.completion_tokens * p_out) / 1_000_000

    def summary(self) -> dict:
        out = {}
        for tier in ("nano", "super"):
            recs = [r for r in self.records if r.tier == tier and r.ok]
            out[tier] = {
                "model": self.model_for(tier),
                "calls": len(recs),
                "tokens": sum(r.total_tokens for r in recs),
                "avg_latency_s": round(sum(r.latency_s for r in recs) / len(recs), 2) if recs else None,
                "cost_usd": sum(self.cost_usd(r) for r in recs),
                "priced": any(self.prices[tier]),
            }
        out["errors"] = [r for r in self.records if not r.ok]
        total_calls = out["nano"]["calls"] + out["super"]["calls"]
        out["nano_share"] = (out["nano"]["calls"] / total_calls) if total_calls else None
        return out


def clean(text: str) -> str:
    """Remove any visible reasoning block some reasoning models include in the reply."""
    text = THINK_RE.sub("", text)
    if "</think>" in text:  # opening tag was cut off
        text = text.split("</think>", 1)[1]
    return text.strip()


def extract_json(text: str | None) -> dict | None:
    if not text:
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        candidate = text[start:end + 1]
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None
