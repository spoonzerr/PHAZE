"""Map: air quality around the world."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from phaze import charts, state, ui
from phaze.bands import band_for
from phaze.cities import REGIONS

VIEWS = {
    "Everywhere": {"latitude": 18, "longitude": 30, "zoom": 1.05},
    "Southeast Asia": {"latitude": 6, "longitude": 108, "zoom": 3.5},
    "South Asia": {"latitude": 25, "longitude": 80, "zoom": 3.6},
    "East Asia": {"latitude": 34, "longitude": 124, "zoom": 3.5},
    "Oceania": {"latitude": -28, "longitude": 145, "zoom": 3.2},
    "Europe": {"latitude": 50, "longitude": 8, "zoom": 3.6},
    "Africa and Middle East": {"latitude": 18, "longitude": 18, "zoom": 2.6},
    "Americas": {"latitude": 18, "longitude": -85, "zoom": 1.9},
    "Custom": {"latitude": 18, "longitude": 30, "zoom": 1.05},
}


def render():
    rows, src = state.world()
    st.html(ui.page_head("Air around the world",
                         f"Live US AQI for {len(rows)} places. Bigger, warmer dots mean dirtier air. "
                         "Hover over a dot to see the details."))
    regions = ["Everywhere"] + REGIONS + (["Custom"] if any(r.get("region") == "Custom" for r in rows) else [])
    region = st.pills("Region", regions, default="Everywhere", label_visibility="collapsed", required=True) or "Everywhere"
    shown = rows if region == "Everywhere" else [r for r in rows if r.get("region") == region]

    left, right = st.columns([1.75, 1], gap="large")
    with left:
        st.pydeck_chart(charts.world_map(shown, view=VIEWS.get(region)), height=560)
        st.html(ui.legend("aqi"))
    with right:
        st.html(ui.section("Worst air here" if region != "Everywhere" else "Worst air right now"))
        st.html(ui.ranking(shown, limit=10))

    if src == "sample":
        st.html('<p class="ph-note">Showing saved sample data because the live feed can\'t be reached.</p>')

    with st.expander("See every reading as a table", icon=":material/table_rows:"):
        df = pd.DataFrame(shown)
        df["level"] = df["us_aqi"].apply(lambda v: band_for(v).label)
        df = df.sort_values("us_aqi", ascending=False)[["name", "country", "region", "us_aqi", "level", "pm2_5", "pm10"]]
        st.dataframe(df, hide_index=True, width="stretch", column_config={
            "name": "Place", "country": "Country", "region": "Region", "level": "Level",
            "us_aqi": st.column_config.ProgressColumn("US AQI", min_value=0, max_value=300, format="%d"),
            "pm2_5": st.column_config.NumberColumn("PM2.5 (µg/m³)", format="%.1f"),
            "pm10": st.column_config.NumberColumn("PM10 (µg/m³)", format="%.1f"),
        })
