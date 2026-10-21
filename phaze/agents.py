"""The four PHAZE agents.

| Agent           | Model tier | Job                                                           |
|-----------------|------------|---------------------------------------------------------------|
| Alert writer    | Nano       | Turns a reading into a short, personal notification           |
| Outdoor planner | Super      | Reads the 48-hour forecast and picks the safest times outside |
| Haze reporter   | Super      | Searches the web (Tavily) and explains what's causing haze    |
| Ask PHAZE   | Nano/Super | Router: Nano sorts the question, then Nano or Super answers   |

Every agent has a rule-based fallback so the app still works in demo mode
(no API key) or if a model call fails. Numbers always come from the data,
never from the model: we compute windows, peaks and bands in Python and
give them to the model to explain.
"""

from __future__ import annotations

import os
from datetime import datetime

from .bands import HEALTHY_LIMIT, band_for, index_name
from .data import peak, windows_below
from .llm import LLM

SAFETY_LINE = "Follow official advisories (e.g. NEA in Singapore). This is not medical advice."

PROFILES = {
    "General public": "a healthy adult",
    "Sensitive (asthma, heart or lung condition)": "someone with asthma or a heart or lung condition",
    "Elderly": "an elderly person",
    "Children": "a parent of young children",
    "Pregnant": "a pregnant person",
}

ACTIVITIES = ["Commute", "Outdoor exercise", "Kids outdoor play", "Errands", "Outdoor event"]


def _fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%a %d %b, %I%p").replace(" 0", " ")
    except Exception:
        return iso


# ------------------------------------------------------------------ Alert writer (Nano)

def write_alert(llm: LLM, place: str, value: float, index: str, profile: str,
                threshold: float = HEALTHY_LIMIT, pm25: float | None = None) -> dict:
    band = band_for(value, index)
    idx = index_name(index)
    fallback = {
        "title": f"{place}: {idx} {round(value)} ({band.label})",
        "message": f"{idx} is {round(value)}, above your limit of {round(threshold)}. {band.advice}",
        "actions": _fallback_actions(band.label, profile),
        "by": "rules",
    }
    who = PROFILES.get(profile, "a healthy adult")
    prompt = (
        f"Write a push notification about haze for {who}.\n"
        f"Place: {place}\nReading: {idx} {round(value)} ({band.label}); alert limit {round(threshold)}.\n"
        + (f"PM2.5: {pm25} µg/m³\n" if pm25 is not None else "")
        + f"Official band advice: {band.advice}\n\n"
        "Reply with JSON only: {\"title\": <max 8 words>, \"message\": <max 30 words, plain and calm>, "
        "\"actions\": [<2-3 short practical actions, max 8 words each>]}. "
        "Do not invent numbers. Do not give medical diagnoses."
    )
    out = llm.chat_json(
        [{"role": "system", "content": "You write short, calm, practical air quality alerts."},
         {"role": "user", "content": prompt}],
        tier="nano", agent="Alert writer", max_tokens=300, temperature=0.4,
    )
    if not out or not out.get("message"):
        return fallback
    actions = out.get("actions") if isinstance(out.get("actions"), list) else fallback["actions"]
    return {
        "title": str(out.get("title") or fallback["title"])[:80],
        "message": str(out["message"])[:300],
        "actions": [str(a)[:80] for a in actions[:3]],
        "by": "nano",
    }


def _fallback_actions(label: str, profile: str) -> list[str]:
    sensitive = profile != "General public"
    if label in ("Good", "Moderate"):
        return ["Carry on as normal", "Check again later"]
    actions = ["Cut down on outdoor exercise", "Keep windows closed if it smells smoky"]
    if sensitive or label in ("Very unhealthy", "Hazardous"):
        actions.insert(0, "Stay indoors where you can")
    if label in ("Very unhealthy", "Hazardous"):
        actions.append("Wear a well-fitted N95 mask outside")
    return actions[:3]


# ------------------------------------------------------------------ Outdoor planner (Super)

def plan_outdoors(llm: LLM, place: str, forecast: dict, profile: str, activity: str,
                  threshold: float = HEALTHY_LIMIT) -> dict:
    times, values = forecast["times"], forecast["us_aqi"]
    windows = windows_below(times, values, threshold, min_hours=2)
    top = peak(times, values)
    best = sorted(windows, key=lambda w: (w["avg"], -w["hours"]))[:3]

    fallback = {
        "summary": _fallback_summary(place, windows, top, threshold),
        "windows": [{"when": f"{_fmt_time(w['start'])} to {_fmt_time(w['end'])}",
                     "why": f"US AQI averages {w['avg']} over {w['hours']} hours"} for w in best],
        "tip": "Plan outdoor time for when the line on the chart is lowest.",
        "by": "rules",
    }

    compact = [f"{t[5:16]} {v}" for t, v in zip(times, values) if v is not None][::2]  # every 2nd hour
    prompt = (
        f"Place: {place}. Person: {PROFILES.get(profile, 'a healthy adult')}. Planned activity: {activity}.\n"
        f"Healthy limit: US AQI {round(threshold)}.\n"
        f"48-hour US AQI forecast (time value, every 2 hours): {', '.join(compact)}\n"
        f"Pre-computed clean windows (at or under the limit): "
        + ("; ".join(f"{w['start'][5:16]} to {w['end'][5:16]}, avg {w['avg']}, max {w['max']}" for w in windows) or "none")
        + (f"\nForecast peak: {top['value']} at {top['time'][5:16]}" if top else "")
        + "\n\nPick the best times for the activity using ONLY the windows above. If there are none, say so "
          "and suggest an indoor alternative. Reply with JSON only: "
          "{\"summary\": <2 sentences>, \"windows\": [{\"when\": <readable time range>, \"why\": <max 15 words>}] "
          "(max 3), \"tip\": <one practical tip, max 20 words>}"
    )
    out = llm.chat_json(
        [{"role": "system", "content": "You are a careful air quality planner. Never invent readings."},
         {"role": "user", "content": prompt}],
        tier="super", agent="Outdoor planner", max_tokens=900, temperature=0.2,
    )
    if not out or not out.get("summary"):
        return fallback
    wins = out.get("windows") if isinstance(out.get("windows"), list) else []
    return {
        "summary": str(out["summary"]),
        "windows": [{"when": str(w.get("when", "")), "why": str(w.get("why", ""))}
                    for w in wins[:3] if isinstance(w, dict)],
        "tip": str(out.get("tip") or ""),
        "by": "super",
    }


def _fallback_summary(place, windows, top, threshold):
    if not windows:
        return (f"The forecast for {place} stays above US AQI {round(threshold)} for the next 48 hours. "
                "Plan indoor alternatives.")
    total = sum(w["hours"] for w in windows)
    peak_txt = f" The worst point is about {top['value']} around {_fmt_time(top['time'])}." if top else ""
    return f"{place} has about {total} hours within the healthy range in the next 48 hours.{peak_txt}"


# ------------------------------------------------------------------ Haze reporter (Tavily + Super)

def _tavily():
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return None
    try:
        from tavily import TavilyClient

        return TavilyClient(api_key=key)
    except Exception:
        return None


def web_search(query: str, max_results: int = 6) -> list[dict]:
    client = _tavily()
    if client is None:
        return []
    try:
        res = client.search(query=query, topic="news", max_results=max_results)
    except TypeError:
        res = client.search(query, max_results=max_results)
    except Exception:
        return []
    out = []
    for r in (res or {}).get("results", [])[:max_results]:
        out.append({
            "title": r.get("title", "Untitled"),
            "url": r.get("url", ""),
            "content": (r.get("content") or "")[:700],
            "published": r.get("published_date") or "",
        })
    return out


def haze_report(llm: LLM, area: str, readings_note: str = "") -> dict:
    query = f"haze air quality {area} fires hotspots latest"
    results = web_search(query)
    if not results:
        return {
            "summary": "Add a TAVILY_API_KEY to search the latest haze news." if not os.getenv("TAVILY_API_KEY")
            else "No recent news found for this area.",
            "causes": [], "outlook": "", "sources": [], "by": "none",
        }
    numbered = "\n\n".join(f"[{i + 1}] {r['title']} ({r['published']})\n{r['content']}" for i, r in enumerate(results))
    prompt = (
        f"Area: {area}\n{readings_note}\n\nRecent news results:\n{numbered}\n\n"
        "Explain the current haze situation for a general reader. Use only these sources and cite them as [n]. "
        "Reply with JSON only: {\"summary\": <3 sentences with citations>, \"causes\": [<up to 3 short points>], "
        "\"outlook\": <1 sentence on what's expected next, or 'Unclear from the sources'>}"
    )
    out = llm.chat_json(
        [{"role": "system", "content": "You summarise news accurately and cite sources. You never add facts that are not in the sources."},
         {"role": "user", "content": prompt}],
        tier="super", agent="Haze reporter", max_tokens=900, temperature=0.2,
    )
    sources = [{"title": r["title"], "url": r["url"]} for r in results]
    if not out or not out.get("summary"):
        return {
            "summary": "Here are the latest articles. Add a NEBIUS_API_KEY to get an AI summary.",
            "causes": [], "outlook": "", "sources": sources, "by": "search only",
        }
    return {
        "summary": str(out["summary"]),
        "causes": [str(c) for c in (out.get("causes") or [])[:3]],
        "outlook": str(out.get("outlook") or ""),
        "sources": sources,
        "by": "super",
    }


# ------------------------------------------------------------------ Ask PHAZE (router)

def route_question(llm: LLM, question: str) -> dict:
    """Nano decides how hard the question is and whether it needs fresh web info."""
    default = {"difficulty": "hard" if len(question) > 140 else "easy",
               "needs_search": any(w in question.lower() for w in ("today", "latest", "news", "why is", "fire", "now"))}
    out = llm.chat_json(
        [{"role": "system", "content": "You classify questions. Reply with JSON only."},
         {"role": "user", "content":
             "Classify this question about air quality or haze.\n"
             "difficulty: 'easy' for definitions, simple facts or yes/no; 'hard' for planning, comparisons or multi-step reasoning.\n"
             "needs_search: true only if it needs news or events from the last few weeks.\n"
             f"Question: {question}\n"
             "JSON: {\"difficulty\": \"easy\"|\"hard\", \"needs_search\": true|false}"}],
        tier="nano", agent="Router", max_tokens=60, temperature=0,
    )
    if not out:
        return default
    return {
        "difficulty": "hard" if str(out.get("difficulty", "")).lower() == "hard" else "easy",
        "needs_search": bool(out.get("needs_search")),
    }


def ask(llm: LLM, question: str, context: str, history: list[dict] | None = None) -> dict:
    route = route_question(llm, question)
    tier = "super" if route["difficulty"] == "hard" else "nano"
    sources = web_search(f"{question} haze air quality") if route["needs_search"] else []
    web = "\n\n".join(f"[{i + 1}] {s['title']}: {s['content']}" for i, s in enumerate(sources))

    system = (
        "You are PHAZE, a friendly air quality assistant. Use the live readings provided. "
        "PSI is Singapore's index (NEA); US AQI is used elsewhere; above 100 is outside the healthy range. "
        "Be concise (under 120 words), practical and calm. Cite web sources as [n] when you use them. "
        "Never invent readings. You don't give medical diagnoses; for health worries suggest seeing a doctor."
    )
    msgs = [{"role": "system", "content": system},
            {"role": "system", "content": f"Live readings:\n{context}"}]
    if web:
        msgs.append({"role": "system", "content": f"Web results:\n{web}"})
    for h in (history or [])[-6:]:
        msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": question})

    answer = llm.chat(msgs, tier=tier, agent=f"Ask ({tier})", max_tokens=700, temperature=0.3)
    if not answer:
        answer = ("I'm in demo mode, so I can't answer free-form questions yet. Add a NEBIUS_API_KEY in your .env "
                  "to switch on Nemotron. Meanwhile, the map and alerts tabs show live readings.")
        tier = "demo"
    return {"answer": answer, "tier": tier, "route": route,
            "sources": [{"title": s["title"], "url": s["url"]} for s in sources]}
