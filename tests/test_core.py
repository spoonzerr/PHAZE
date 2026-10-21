"""Offline tests: run with  python -m pytest -q"""

import json
from pathlib import Path
from types import SimpleNamespace

from phaze import agents
from phaze.bands import band_for, is_unhealthy
from phaze.cities import DEFAULT_CITIES
from phaze.data import (parse_open_meteo_current, parse_open_meteo_hourly, parse_sg_psi, sample_forecast,
                            sample_world, sg_overall, windows_below)
from phaze.llm import LLM, clean, extract_json
from phaze.notify import AlertState, format_alert

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- bands

def test_psi_bands():
    assert band_for(50, "psi").label == "Good"
    assert band_for(51, "psi").label == "Moderate"
    assert band_for(101, "psi").label == "Unhealthy"
    assert band_for(201, "psi").label == "Very unhealthy"
    assert band_for(301, "psi").label == "Hazardous"
    assert band_for(None).label == "No data"


def test_aqi_bands():
    assert band_for(120).label == "Unhealthy for sensitive groups"
    assert band_for(180).label == "Unhealthy"
    assert is_unhealthy(101) and not is_unhealthy(100) and not is_unhealthy(None)


# ---------------------------------------------------------------- data parsing

def test_parse_sg_psi_sample():
    psi = parse_sg_psi(json.loads((ROOT / "sample_data/sg_psi.json").read_text()))
    assert set(psi["regions"]) == {"north", "south", "east", "west", "central"}
    assert psi["regions"]["west"]["psi"] == 141
    assert sg_overall(psi) == 141


def test_parse_open_meteo_single_and_list():
    one = {"current": {"time": "2026-10-20T20:00", "us_aqi": 77, "pm2_5": 23.4, "pm10": 30.0}}
    rows = parse_open_meteo_current(one, DEFAULT_CITIES[:1])
    assert rows[0]["us_aqi"] == 77 and rows[0]["name"] == "Singapore"
    many = [one, {"current": {"us_aqi": None, "pm2_5": float("nan")}}]
    rows = parse_open_meteo_current(many, DEFAULT_CITIES[:2])
    assert rows[1]["us_aqi"] is None and rows[1]["pm2_5"] is None


def test_parse_hourly_starts_at_current_hour():
    payload = {"current": {"time": "2026-10-21T02:15"},
               "hourly": {"time": [f"2026-10-21T{h:02d}:00" for h in range(6)],
                          "us_aqi": [10, 20, 30, 40, 50, 60], "pm2_5": [1, 2, 3, 4, 5, 6]}}
    fc = parse_open_meteo_hourly(payload, hours=3)
    assert fc["times"][0] == "2026-10-21T02:00" and fc["us_aqi"] == [30, 40, 50]


def test_sample_world_covers_all_defaults():
    rows = sample_world(DEFAULT_CITIES)
    assert len(rows) == len(DEFAULT_CITIES)
    assert all(r["us_aqi"] is not None for r in rows)


def test_windows_below():
    times = [f"t{i}" for i in range(8)]
    vals = [120, 90, 80, 70, 130, 60, 140, 50]
    wins = windows_below(times, vals, 100, min_hours=2)
    assert len(wins) == 1 and wins[0]["start"] == "t1" and wins[0]["hours"] == 3 and wins[0]["max"] == 90


def test_sample_forecast_shape():
    fc = sample_forecast(1.35, 103.8, hours=48)
    assert len(fc["times"]) == len(fc["us_aqi"]) == 48


# ---------------------------------------------------------------- llm helpers

def test_clean_and_extract_json():
    assert clean("<think>hmm</think> Hello") == "Hello"
    assert clean("reasoning cut off</think>Answer") == "Answer"
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"title": "x"} hope that helps') == {"title": "x"}
    assert extract_json("no json here") is None


class FakeClient:
    """Stands in for the OpenAI client so we can test routing without a network."""

    def __init__(self, replies):
        self.replies = replies
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages, **kw):
        self.calls.append(model)
        text = self.replies.pop(0) if self.replies else "{}"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )


def make_llm(replies):
    llm = LLM(api_key=None, nano_model="nano-x", super_model="super-x")
    llm._client = FakeClient(replies)
    return llm


def test_demo_mode_fallbacks(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    llm = LLM()
    assert not llm.live
    alert = agents.write_alert(llm, "Singapore (West)", 141, "psi", "General public")
    assert alert["by"] == "rules" and "141" in alert["title"]
    plan = agents.plan_outdoors(llm, "Singapore", sample_forecast(1.35, 103.8), "General public", "Commute")
    assert plan["by"] == "rules" and plan["summary"]


def test_alert_uses_nano():
    llm = make_llm(['{"title": "Haze is up", "message": "PSI 141 in the west.", "actions": ["Stay in"]}'])
    alert = agents.write_alert(llm, "Singapore (West)", 141, "psi", "Elderly")
    assert alert["by"] == "nano" and llm._client.calls == ["nano-x"]
    assert llm.summary()["nano"]["calls"] == 1 and llm.summary()["nano"]["tokens"] == 120


def test_planner_uses_super():
    llm = make_llm(['{"summary": "Go early.", "windows": [{"when": "Wed 2PM to 5PM", "why": "lowest"}], "tip": "Mask"}'])
    plan = agents.plan_outdoors(llm, "Singapore", sample_forecast(1.35, 103.8), "Children", "Kids outdoor play")
    assert plan["by"] == "super" and llm._client.calls == ["super-x"]


def test_router_sends_hard_questions_to_super(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    llm = make_llm(['{"difficulty": "hard", "needs_search": false}', "Here is a plan."])
    res = agents.ask(llm, "Plan my week of runs around the haze", "context")
    assert res["tier"] == "super" and llm._client.calls == ["nano-x", "super-x"]
    assert llm.summary()["nano_share"] == 0.5

    llm = make_llm(['{"difficulty": "easy", "needs_search": false}', "PSI is an index."])
    res = agents.ask(llm, "What is PSI?", "context")
    assert res["tier"] == "nano" and llm._client.calls == ["nano-x", "nano-x"]


def test_model_error_is_logged_and_falls_back():
    llm = make_llm([])

    def boom(**kw):
        raise RuntimeError("401 unauthorized")

    llm._client.chat.completions.create = boom
    alert = agents.write_alert(llm, "Jakarta", 150, "aqi", "General public")
    assert alert["by"] == "rules"
    assert llm.summary()["errors"] and "401" in llm.summary()["errors"][0].error


# ---------------------------------------------------------------- notifications

def test_alert_state_dedupes(tmp_path):
    st = AlertState(tmp_path / "s.json", cooldown_hours=3)
    t0 = 1_000_000
    assert st.should_alert("sg", 120, 100, "Unhealthy", now=t0)
    st.mark("sg", 120, "Unhealthy", now=t0)
    assert not st.should_alert("sg", 125, 100, "Unhealthy", now=t0 + 600)         # same episode
    assert st.should_alert("sg", 210, 100, "Very unhealthy", now=t0 + 900)         # got worse
    assert st.should_alert("sg", 125, 100, "Unhealthy", now=t0 + 3 * 3600 + 1)     # still bad after cooldown
    assert not st.should_alert("sg", 80, 100, "Moderate", now=t0 + 1000)           # back to healthy
    assert st.should_alert("sg", 130, 100, "Unhealthy", now=t0 + 1200)             # new episode
    st.save()
    assert AlertState(tmp_path / "s.json").state["sg"]["band"] == "Unhealthy"


def test_format_alert():
    text = format_alert({"title": "Haze", "message": "PSI high.", "actions": ["Stay in"]})
    assert "Haze" in text and "• Stay in" in text
