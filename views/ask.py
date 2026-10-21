"""Ask: questions about haze, answered with today's readings."""

from __future__ import annotations

import streamlit as st

from phaze import state, ui
from phaze.agents import ask

EXAMPLES = [
    "Is it safe to jog in Singapore this evening?",
    "What's the difference between PSI and PM2.5?",
    "Why does haze get worse around September?",
]

AVATAR = "static/phaze-icon.svg"


def _context() -> str:
    ss = st.session_state
    psi = state.sg()
    rows, _ = state.world()
    lines = [f"Singapore 24h PSI by region ({psi.get('timestamp')}): "
             + ", ".join(f"{k} {v['psi']}" for k, v in psi["regions"].items())]
    top = sorted([r for r in rows if r["us_aqi"] is not None], key=lambda r: -r["us_aqi"])
    lines.append("US AQI now: " + ", ".join(f"{r['name']} {round(r['us_aqi'])}" for r in top))
    lines.append(f"User's alert limit: {ss.threshold}. Who it's for: {ss.profile}. "
                 f"Places they watch: {', '.join(ss.watchlist)}")
    return "\n".join(lines)


def render():
    ss = st.session_state
    st.html(ui.page_head("Ask PHAZE",
                         "Ask about haze, health precautions or your plans. Answers use today's readings."))

    for m in ss.chat:
        with st.chat_message(m["role"], avatar=AVATAR if m["role"] == "assistant" else ":material/person:"):
            st.markdown(m["content"])
            if m.get("meta"):
                st.html(ui.by(m["meta"], ai=m.get("ai", True)))

    picked = None
    if not ss.chat:
        st.html('<p class="ph-note">Try one of these:</p>')
        with st.container(horizontal=True, gap="small"):
            for i, ex in enumerate(EXAMPLES):
                if st.button(ex, key=f"example_{i}", icon=":material/chat_bubble:"):
                    picked = ex

    question = st.chat_input("Ask about haze, air quality or your plans") or picked
    if question:
        ss.chat.append({"role": "user", "content": question})
        with st.spinner("Thinking..."):
            res = ask(ss.llm, question, _context(),
                      history=[{"role": m["role"], "content": m["content"]} for m in ss.chat[:-1]])
        answer = res["answer"]
        if res["sources"]:
            answer += "\n\n" + "\n".join(f"{i + 1}. [{s['title']}]({s['url']})" for i, s in enumerate(res["sources"]))
        meta = {"nano": "Answered by Nemotron Nano, as a quick question",
                "super": "Answered by Nemotron Super, as a question that needs more reasoning",
                "demo": "AI is off, so this is a standard reply"}[res["tier"]]
        if res["route"].get("needs_search") and res["sources"]:
            meta += ", with a Tavily web search"
        ss.chat.append({"role": "assistant", "content": answer, "meta": meta, "ai": res["tier"] != "demo"})
        st.rerun()

    if ss.chat and st.button("Start over", icon=":material/restart_alt:", type="tertiary"):
        ss.chat = []
        st.rerun()
