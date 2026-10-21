"""Charts and the world map, styled to match the rest of PHAZE."""

from __future__ import annotations

import math

import altair as alt
import pandas as pd
import pydeck as pdk

from .bands import band_for, bands_for

DUSK = "#1E2D3B"
SLATE = "#5A6976"
LINE = "#D3DADF"
SKY = "#2D6CA2"
FONT = '"Atkinson Hyperlegible Next", system-ui, sans-serif'


def _base_config(chart: alt.Chart) -> alt.Chart:
    return (chart.configure(font=FONT, background="transparent")
            .configure_view(stroke=None)
            .configure_axis(labelColor=SLATE, titleColor=SLATE, labelFontSize=12, titleFontSize=12,
                            titleFontWeight="normal", gridColor="#E3E8EB", domain=False, tickColor=LINE)
            .configure_text(font=FONT))


def forecast(times: list[str], values: list, threshold: float, height: int = 300) -> alt.Chart:
    """US AQI forecast over the health bands, with your limit and the peak marked."""
    df = pd.DataFrame({"time": pd.to_datetime(times), "aqi": values}).dropna()
    if df.empty:
        return alt.Chart(pd.DataFrame({"x": []})).mark_point()
    top = max(150.0, float(df["aqi"].max()) * 1.18, threshold * 1.25)
    top = math.ceil(top / 50) * 50
    y = alt.Y("aqi:Q", title="US AQI", scale=alt.Scale(domain=[0, top], nice=False),
              axis=alt.Axis(values=list(range(0, int(top) + 1, 50))))

    rows, lower = [], 0
    for b in bands_for("aqi"):
        upper = top if b.upper == float("inf") else min(b.upper, top)
        if lower < top:
            rows.append({"y0": lower, "y1": upper, "color": b.color_hex, "band": b.label})
        lower = b.upper
    bands = alt.Chart(pd.DataFrame(rows)).mark_rect(opacity=.13).encode(
        y=alt.Y("y0:Q", scale=alt.Scale(domain=[0, top], nice=False)), y2="y1:Q",
        color=alt.Color("color:N", scale=None))

    # ticks every 6 hours: the day's name at midnight, "6 AM" / "Noon" / "6 PM" otherwise
    ticks = [alt.DateTime(year=t.year, month=t.month, date=t.day, hours=t.hour)
             for t in df["time"] if t.hour % 6 == 0]
    label = ("hours(datum.value) == 0 ? timeFormat(datum.value, '%a') : hours(datum.value) == 12 ? 'Noon' : "
             "(hours(datum.value) % 12) + (hours(datum.value) < 12 ? ' AM' : ' PM')")
    x = alt.X("time:T", title=None, axis=alt.Axis(values=ticks, labelExpr=label, labelAngle=0, grid=False,
                                                  labelOverlap=True, labelPadding=6))
    tooltip = [alt.Tooltip("time:T", title="Time", format="%a %d %b, %I %p"),
               alt.Tooltip("aqi:Q", title="US AQI", format=".0f")]
    line = alt.Chart(df).mark_line(color=DUSK, strokeWidth=2.6, interpolate="monotone").encode(x=x, y=y, tooltip=tooltip)
    hover = alt.Chart(df).mark_point(size=90, opacity=0).encode(x=x, y=y, tooltip=tooltip)

    limit = pd.DataFrame({"aqi": [threshold], "label": [f"Your limit, {round(threshold)}"]})
    limit_rule = alt.Chart(limit).mark_rule(color=DUSK, strokeDash=[6, 5], opacity=.55, strokeWidth=1.5).encode(y="aqi:Q")
    limit_text = alt.Chart(limit).mark_text(align="right", dx=-4, dy=-8, color=DUSK, fontSize=12, fontWeight=600).encode(
        y="aqi:Q", x=alt.value("width"), text="label:N")

    peak = df.loc[[df["aqi"].idxmax()]].copy()
    peak["label"] = peak.apply(lambda r: f"Peak {round(r['aqi'])}", axis=1)
    peak_color = band_for(float(peak["aqi"].iloc[0])).color_hex
    peak_dot = alt.Chart(peak).mark_point(filled=True, size=110, color=peak_color, stroke="white", strokeWidth=2,
                                          opacity=1).encode(x=x, y=y)
    peak_text = alt.Chart(peak).mark_text(dy=-16, color=DUSK, fontSize=12.5, fontWeight=700).encode(x=x, y=y, text="label:N")

    now = df.iloc[[0]].copy()
    now["label"] = "Now"
    now_rule = alt.Chart(now).mark_rule(color=SKY, strokeWidth=2, opacity=.8).encode(x=x)
    now_text = alt.Chart(now).mark_text(align="left", dx=5, y=8, color=SKY, fontSize=12, fontWeight=700).encode(x=x, text="label:N")

    chart = alt.layer(bands, limit_rule, now_rule, line, hover, peak_dot, peak_text, limit_text, now_text).properties(
        height=height)
    return _base_config(chart)


def world_map(rows: list[dict], height: int = 520, view: dict | None = None) -> pdk.Deck:
    """Dots sized and coloured by US AQI on a quiet light basemap."""
    data = []
    for r in rows:
        v = r.get("us_aqi")
        b = band_for(v)
        data.append({
            **{k: r.get(k) for k in ("name", "country", "lat", "lon")},
            "aqi": "–" if v is None else round(v),
            "pm": "–" if r.get("pm2_5") is None else r["pm2_5"],
            "band": b.label,
            "color": list(b.rgb) + [225],
            "radius": 18000 + (v or 20) * 950,
        })
    view = view or {"latitude": 12, "longitude": 102, "zoom": 2.3}
    halo = pdk.Layer("ScatterplotLayer", data=data, get_position="[lon, lat]", get_fill_color="color",
                     get_radius="radius", radius_scale=2.1, radius_min_pixels=10, radius_max_pixels=46, opacity=.16,
                     pickable=False)
    dots = pdk.Layer("ScatterplotLayer", data=data, get_position="[lon, lat]", get_fill_color="color",
                     get_radius="radius", radius_min_pixels=5, radius_max_pixels=26, pickable=True, stroked=True,
                     get_line_color=[255, 255, 255, 235], line_width_min_pixels=1.5)
    tooltip = {
        "html": "<b style='font-size:15px'>{name}</b><br/><span style='opacity:.8'>{country}</span><br/>"
                "US AQI <b>{aqi}</b>, {band}<br/>PM2.5 {pm} µg/m³",
        "style": {"backgroundColor": "#1E2D3B", "color": "#F9FAFA", "fontFamily": FONT, "fontSize": "13px",
                  "borderRadius": "12px", "padding": "10px 12px"},
    }
    return pdk.Deck(layers=[halo, dots], initial_view_state=pdk.ViewState(**view), map_provider="carto",
                    map_style=pdk.map_styles.CARTO_LIGHT, tooltip=tooltip)
