"""Offline tests for the interface helpers: python -m pytest -q"""

import base64
import re

from phaze import ui
from phaze.bands import band_for, scale_position
from phaze.cities import DEFAULT_CITIES
from phaze.data import fetch_forecasts, parse_sg_psi, sample_forecast
from phaze.guidance import trend, verdicts
from phaze.watch import SINGAPORE, watch_readings

PSI = parse_sg_psi({"data": {"regionMetadata": [], "items": [{"timestamp": "2026-10-20T20:00:00+08:00", "readings": {
    "psi_twenty_four_hourly": {"north": 85, "south": 103, "east": 106, "west": 141, "central": 122},
    "pm25_twenty_four_hourly": {"north": 42, "south": 57, "east": 61, "west": 94, "central": 75}}}]}})


# ---------------------------------------------------------------- bands and guidance

def test_band_levels_line_up_across_scales():
    assert band_for(141, "psi").level == 3 and band_for(141, "aqi").level == 2
    assert band_for(20).level == 0 and band_for(400, "psi").level == 5 and band_for(None).level == -1


def test_scale_position_is_equal_width_per_band():
    assert scale_position(0, "psi") == 0
    assert scale_position(50, "psi") == 0.2          # end of the first of five bands
    assert scale_position(150, "psi") == 0.5         # half way through Unhealthy (101-200)
    assert scale_position(900) == 1.0 and scale_position(None) is None


def test_verdicts_get_stricter_and_respect_sensitive_groups():
    calm = {v.activity: v.state for v in verdicts(0)}
    assert set(calm.values()) == {"go"}
    general = {v.activity: v.state for v in verdicts(2, "General public")}
    sensitive = {v.activity: v.state for v in verdicts(2, "Elderly")}
    assert general["Exercise outdoors"] == "careful" and sensitive["Exercise outdoors"] == "avoid"
    assert {v.state for v in verdicts(5)} == {"avoid"}
    assert verdicts(-1) == []


def test_trend_directions():
    assert trend([100] + [140] * 12).direction == "rising"
    assert trend([140] + [100] * 12).direction == "easing"
    assert trend([120, 118, 122, 121, 119]).direction == "steady"
    assert trend([None, 100]).direction == "unknown"
    t = trend([100, 120, 180, 150] + [110] * 10)
    assert t.peak == 180 and t.peak_index == 2


# ---------------------------------------------------------------- watchlist readings

def test_singapore_is_one_reading_using_the_worst_region():
    rows = [{"name": "Jakarta", "country": "Indonesia", "us_aqi": 141, "pm2_5": 52, "time": "t"}]
    out = watch_readings([SINGAPORE, "Jakarta, Indonesia", "Nowhere, Atlantis"], PSI, rows)
    assert [r["key"] for r in out] == [SINGAPORE, "Jakarta, Indonesia"]
    sg = out[0]
    assert sg["value"] == 141 and sg["index"] == "psi" and sg["region"] == "west" and sg["place"] == "Singapore (west)"
    assert out[1]["index"] == "aqi" and out[1]["value"] == 141


def test_forecasts_fall_back_to_sample_curves_near_today(monkeypatch):
    import phaze.data as data

    def offline(*a, **k):
        raise ConnectionError("offline")

    monkeypatch.setattr(data.requests, "get", offline)
    out = fetch_forecasts(DEFAULT_CITIES[:2], current={"Singapore, Singapore": 128})
    sg = out["Singapore, Singapore"]
    assert sg["source"] == "sample" and len(sg["us_aqi"]) == 48 and sg["us_aqi"][0] == 128


# ---------------------------------------------------------------- HTML components

def test_text_is_escaped_everywhere():
    evil = '<img src=x onerror="alert(1)">'
    log = [{"title": evil, "message": evil, "actions": [evil], "by": "nano", "value": 150, "index": "aqi", "at": "1 PM"}]
    for html in (ui.sky(evil, 150, "aqi"), ui.alert_timeline(log), ui.section(evil, evil),
                 ui.report({"summary": evil, "causes": [evil], "sources": [{"title": evil, "url": "https://a.b/c"}]}),
                 ui.plan({"summary": evil, "windows": [{"when": evil, "why": evil}], "tip": evil})):
        assert "<img src=x" not in html and "&lt;img" in html


def test_sky_reflects_the_reading():
    clear, hazy = ui.sky("Tokyo", 30, "aqi"), ui.sky("Singapore", 141, "psi")
    assert "The air in Tokyo is good" in clear and "ph-sun__bar" not in clear
    assert "The air in Singapore is unhealthy" in hazy and hazy.count("ph-sun__bar") == 2 and ">PSI<" in hazy
    assert "has no reading" in ui.sky("Kuching", None, "aqi")


def test_drawings_are_data_uri_images():
    html = ui.sky("Tokyo", 30, "aqi")
    assert "<svg" not in html  # st.html removes inline SVG
    uris = re.findall(r'src="data:image/svg\+xml;base64,([^"]+)"', html)
    assert len(uris) == 2 and "<path" in base64.b64decode(uris[0]).decode()
    assert ui.sparkline([1, 2, 3]).startswith('<img class="ph-spark"') and ui.sparkline([5]) == ""


def test_hours_strip_marks_clear_hours():
    fc = sample_forecast(1.35, 103.8, 48, 90)
    html = ui.hours(fc["times"], fc["us_aqi"], 100)
    assert html.count('class="ph-hours__cell') == 48
    clear = sum(1 for v in fc["us_aqi"] if v <= 100)
    assert html.count(" is-ok") == clear and f"{clear} of the next 48 hours" in html


def test_ranking_is_sorted_worst_first():
    rows = [{"name": "A", "country": "x", "us_aqi": 40}, {"name": "B", "country": "y", "us_aqi": 240},
            {"name": "C", "country": "z", "us_aqi": None}]
    html = ui.ranking(rows)
    assert html.index(">B<") < html.index(">A<") and ">C<" not in html
