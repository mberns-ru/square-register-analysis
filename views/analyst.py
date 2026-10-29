from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import theme as T
from core.analyst import N_FUNCTIONS, Answer, Period, ask, claude_available
from core.data import Ctx
from core.metrics import REGISTRY, Metrics


@st.cache_resource(show_spinner=False)
def _metrics(_tx: pd.DataFrame, _items: pd.DataFrame, key: tuple) -> Metrics:
    return Metrics(_tx, _items)


def _render_answer(q: str, a: Answer, i: int) -> None:
    st.markdown(f'<div style="text-align:right;margin:10px 0 6px 0"><span class="bubble-q">{T.esc(q)}</span></div>',
                unsafe_allow_html=True)
    with st.container(key=f"card_ans_{i}"):
        st.markdown(a.text.replace("$", "\\$"))
        if a.bars:
            fig = go.Figure(go.Bar(x=[k for k, _ in a.bars], y=[v for _, v in a.bars],
                                   marker=dict(color=[T.INDIGO if v >= 0 else T.ORANGE for _, v in a.bars],
                                               cornerradius=5),
                                   text=[f"{v:+.1f}%" for _, v in a.bars], textposition="outside",
                                   hovertemplate="%{x}: %{y:+.1f}%<extra></extra>"))
            fig.update_yaxes(ticksuffix="%", zeroline=True, zerolinecolor="#D9DBEE")
            ymax = max(abs(v) for _, v in a.bars) * 1.3 or 1
            fig.update_yaxes(range=[-ymax, ymax])
            T.chart(fig, 220, key=f"ans_bars_{i}")
        for title, df in a.tables:
            with st.expander(title, expanded=not a.bars and len(a.tables) == 1):
                st.dataframe(df.round(2), hide_index=True, width="stretch")
        trace = "<br>".join(T.esc(c) for c in a.calls) or "(no metric calls)"
        rng = f"Range: {T.esc(a.range_note)}<br>" if a.range_note else ""
        st.markdown(f'<div class="trace">{rng}Calculated with:<br>{trace}<br>Voided transactions excluded; '
                    f'refunds netted against payments. Engine: {T.esc(a.engine)}.</div>', unsafe_allow_html=True)


def render(ctx: Ctx) -> None:
    T.page_header("AI analyst", "Ask about your sales in plain language")
    if not ctx.has_tx:
        st.info("Upload transaction exports so the analyst has something to work with.")
        return
    if "analyst_log" not in st.session_state:
        st.session_state.analyst_log = []
    m = _metrics(ctx.tx_all, ctx.items_all, (len(ctx.tx_all), len(ctx.items_all), str(ctx.tx_all["Day"].max())))
    dmin, dmax = ctx.tx_all["Day"].min().date(), ctx.tx_all["Day"].max().date()
    default = Period(ctx.start, ctx.end, ctx.range_label())

    left, right = st.columns([2.1, 1], gap="medium")
    with right:
        with st.container(key="card_guard"):
            T.card_header("Guardrails", "How answers are produced")
            st.markdown(T.progress_bars([
                ("Approved metrics only", 1, f"{N_FUNCTIONS} functions"),
                ("Every answer traceable", 1, "calls + dates shown"),
                ("Scoped to this business", 1, "read-only"),
                ("Logged", 1, f"{len(st.session_state.analyst_log)} questions"),
            ], colors=[T.INDIGO, T.LAVENDER, T.ORANGE, T.PEACH]), unsafe_allow_html=True)
            engine = "Claude picks the metric calls" if claude_available() else \
                "Built-in planner (set ANTHROPIC_API_KEY to use Claude)"
            st.caption(engine)
        with st.container(key="card_fns"):
            T.card_header("Approved functions", "The only way the analyst can read your data")
            for f in REGISTRY.values():
                st.markdown(f'<div style="margin:0 0 8px 0"><code style="color:{T.INDIGO};background:#F3F4FD;'
                            f'border-radius:6px;padding:1px 6px;font-size:.75rem">{f.name}</code>'
                            f'<div class="card-sub" style="margin:2px 0 0 2px">{T.esc(f.description)}</div></div>',
                            unsafe_allow_html=True)
        if st.session_state.analyst_log:
            log = pd.DataFrame([{"Asked": t, "Question": q, "Calls": len(a.calls)}
                                for t, q, a in st.session_state.analyst_log])
            st.download_button("Download question log", log.to_csv(index=False).encode(), "analyst_log.csv",
                               "text/csv", width="stretch")

    with left:
        last_month = pd.Timestamp(dmax).strftime("%B")
        prev_month = (pd.Timestamp(dmax) - pd.DateOffset(months=1)).strftime("%B")
        suggestions = [
            f"Why was {last_month} slower than {prev_month}?",
            f"Top 10 items in {last_month}",
            "Flag unusual days in the last 90 days",
            "Why were there refunds this year?",
            f"Average ticket by weekday in {last_month}",
            "Net sales by month this year",
        ]
        if not st.session_state.analyst_log:
            with st.container(key="card_intro"):
                T.card_header("Try asking", "Answers only use numbers from approved metric functions, with the "
                                            "date range shown every time.")
                cols = st.columns(2)
                for i, s in enumerate(suggestions):
                    if cols[i % 2].button(s, key=f"sug_{i}", type="secondary", width="stretch"):
                        st.session_state.pending_q = s
                        st.rerun()

        for i, (_, q, a) in enumerate(st.session_state.analyst_log):
            _render_answer(q, a, i)

        q = st.chat_input("Ask a question, e.g. why was August slow?")
        q = q or st.session_state.pop("pending_q", None)
        if q:
            hist = []
            for _, pq, pa in st.session_state.analyst_log[-3:]:
                hist += [{"role": "user", "content": pq}, {"role": "assistant", "content": pa.text}]
            with st.spinner("Running approved metrics…"):
                try:
                    ans = ask(q, m, default, dmin, dmax, ctx.window, hist)
                except Exception as e:  # noqa: BLE001
                    ans = Answer(f"I couldn't answer that with the approved metrics ({e}). Try naming a month, "
                                 f"a metric (sales, transactions, tips, refunds) or a breakdown (by item, by daypart).")
            st.session_state.analyst_log.append((datetime.now().strftime("%Y-%m-%d %H:%M"), q, ans))
            st.rerun()
        if st.session_state.analyst_log and st.button("Clear conversation", type="secondary"):
            st.session_state.analyst_log = []
            st.rerun()
