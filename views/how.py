"""How it works: which Nemotron model does which job, and what this session has used."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from phaze import ui

JOBS = [
    ("Alert writer", "Turns a reading into a short, personal alert", "nano",
     "Runs on every alert, so it has to be quick and cheap."),
    ("Question router", "Decides if a question is simple or needs more thought", "nano",
     "A tiny sorting job. A big model would be wasted here."),
    ("Ask PHAZE", "Answers your questions with today's readings", "both",
     "Simple questions stay on Nano. Harder ones go to Super."),
    ("Outdoor planner", "Finds the clearest times in the 48-hour forecast", "super",
     "Weighs a whole forecast against your plans and who you are."),
    ("Haze reporter", "Explains the latest news, with sources", "super",
     "Reads several articles from Tavily and cites them accurately."),
]


def render():
    ss = st.session_state
    llm = ss.llm
    st.html(ui.page_head("How PHAZE works",
                         "Two NVIDIA Nemotron models on Nebius Token Factory, each doing the jobs it's best at. "
                         "All the numbers come from official data, and the models explain them."))

    st.html(ui.section("Who does what"))
    st.html(ui.flow(JOBS))
    st.html(f'<p class="ph-note">Models: {ui.esc(llm.nano_model)} and {ui.esc(llm.super_model)}, '
            f'through {ui.esc(llm.base_url)}</p>')

    st.space("small")
    st.html(ui.section("This session", "Live numbers from the model calls PHAZE has made since you opened it."))
    s = llm.summary()
    calls = s["nano"]["calls"] + s["super"]["calls"]
    tokens = s["nano"]["tokens"] + s["super"]["tokens"]
    lat = [x for x in (s["nano"]["avg_latency_s"], s["super"]["avg_latency_s"]) if x is not None]
    cost = s["nano"]["cost_usd"] + s["super"]["cost_usd"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Model calls", calls, border=True)
    c2.metric("Handled by Nano", f"{round(s['nano_share'] * 100)}%" if s["nano_share"] is not None else "–", border=True)
    c3.metric("Tokens used", f"{tokens:,}", border=True)
    c4.metric("Estimated cost", f"${cost:.4f}" if calls else "–", border=True,
              help="Uses the prices in .env. Super's price is only counted if you set it.")
    if calls:
        st.html(ui.split(s["nano"]["calls"], s["super"]["calls"]))
    if llm.records:
        with st.expander("Every call, newest first", icon=":material/receipt_long:"):
            st.dataframe(pd.DataFrame([{
                "Job": r.agent, "Model": r.model, "Tokens in": r.prompt_tokens, "Tokens out": r.completion_tokens,
                "Seconds": round(r.latency_s, 2), "Result": "OK" if r.ok else f"Failed: {r.error[:60]}",
            } for r in reversed(llm.records)]), hide_index=True, width="stretch")
    elif not llm.live:
        st.html(ui.empty("AI is off", "Add NEBIUS_API_KEY to your .env file and restart PHAZE to use Nemotron. "
                                      "Until then, alerts and plans use standard wording."))

    st.space("small")
    st.html(ui.section("Where the data comes from"))
    st.html(ui.data_sources())
    if lat:
        st.html(f'<p class="ph-note">Average reply time this session: {sum(lat) / len(lat):.2f} seconds.</p>')
