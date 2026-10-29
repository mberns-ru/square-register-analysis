"""AI analyst: a full-width, collapsible panel shown at the top of every page."""

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


def ask_from_anywhere(question: str) -> None:
    """Send a question to the panel (used by buttons and search boxes on other pages)."""
    st.session_state.pending_q = question
    st.session_state.analyst_open = True
    st.rerun()


def _render_answer(q: str, a: Answer, i: int) -> None:
    with st.container(key=f"ans_{i}"):
        st.markdown(f'<div style="margin:0 0 8px 0"><span class="bubble-q">{T.esc(q)}</span></div>',
                    unsafe_allow_html=True)
        left, right = st.columns([1.5, 1], gap="large") if a.bars else (st.container(), None)
        with left:
            st.markdown(a.text.replace("$", "\\$"))
            for title, df in a.tables:
                with st.expander(title, expanded=not a.bars and len(a.tables) == 1):
                    st.dataframe(df.round(2), hide_index=True, width="stretch")
        if right is not None:
            with right:
                fig = go.Figure(go.Bar(x=[k for k, _ in a.bars], y=[v for _, v in a.bars],
                                       marker=dict(color=[T.INDIGO if v >= 0 else T.ORANGE for _, v in a.bars],
                                                   cornerradius=5),
                                       text=[f"{v:+.1f}%" for _, v in a.bars], textposition="outside",
                                       hovertemplate="%{x}: %{y:+.1f}%<extra></extra>"))
                ymax = max(abs(v) for _, v in a.bars) * 1.3 or 1
                fig.update_yaxes(ticksuffix="%", zeroline=True, zerolinecolor=T.LINE, range=[-ymax, ymax])
                T.chart(fig, 220, key=f"ans_bars_{i}", bg=T.TINT)
        trace = "<br>".join(T.esc(c) for c in a.calls) or "(no metric calls)"
        rng = f"Range: {T.esc(a.range_note)}<br>" if a.range_note else ""
        st.markdown(f'<div class="trace">{rng}Calculated with:<br>{trace}<br>Voided transactions excluded; '
                    f'refunds netted against payments. Engine: {T.esc(a.engine)}.</div>', unsafe_allow_html=True)


def _guardrails() -> None:
    st.markdown(T.progress_bars([
        ("Approved metrics only", 1, f"{N_FUNCTIONS} functions"),
        ("Every answer traceable", 1, "calls + dates shown"),
        ("Scoped to this business", 1, "read-only"),
        ("Logged", 1, f"{len(st.session_state.analyst_log)} questions"),
    ], colors=[T.INDIGO, T.LAVENDER, T.ORANGE, T.PEACH]), unsafe_allow_html=True)
    st.caption("Claude picks the metric calls." if claude_available()
               else "Built-in planner. Set ANTHROPIC_API_KEY to have Claude plan the calls.")
    st.markdown("**Approved functions**")
    for f in REGISTRY.values():
        st.markdown(f'<div style="margin:0 0 6px 0"><code style="color:{T.INDIGO};background:{T.TINT};'
                    f'border-radius:6px;padding:1px 6px;font-size:.75rem">{f.name}</code>'
                    f'<div class="card-sub" style="margin:2px 0 0 2px">{T.esc(f.description)}</div></div>',
                    unsafe_allow_html=True)


def render_panel(ctx: Ctx) -> None:
    if not ctx.has_tx:
        return
    st.session_state.setdefault("analyst_log", [])
    st.session_state.setdefault("analyst_open", True)
    log = st.session_state.analyst_log
    is_open = st.session_state.analyst_open

    m = _metrics(ctx.tx_all, ctx.items_all, (len(ctx.tx_all), len(ctx.items_all), str(ctx.tx_all["Day"].max())))
    dmin, dmax = ctx.tx_all["Day"].min().date(), ctx.tx_all["Day"].max().date()

    # Answer any question sent from elsewhere (search box, "Ask why" buttons) before drawing
    pending = st.session_state.pop("pending_q", None)
    if pending:
        _answer(pending, m, ctx, dmin, dmax)

    with st.container(key="card_analyst"):
        h1, h2, h3 = st.columns([6, 1.3, 1.1], vertical_alignment="center")
        with h1:
            sub = ("Ask about your sales in plain language. Answers use only approved metrics and show their dates."
                   if is_open else
                   (f"Last asked: “{log[-1][1]}”" if log else "Collapsed. Expand to ask a question about your sales."))
            st.markdown(f'<p class="card-title"><span style="color:{T.INDIGO}">✦</span> AI analyst</p>'
                        f'<p class="card-sub">{T.esc(sub)}</p>', unsafe_allow_html=True)
        with h2.popover("Guardrails", icon=":material/verified_user:", width="stretch"):
            _guardrails()
        if h3.button("Collapse" if is_open else "Expand", key="analyst_toggle", type="secondary", width="stretch",
                     icon=":material/expand_less:" if is_open else ":material/expand_more:"):
            st.session_state.analyst_open = not is_open
            st.rerun()

        if not is_open:
            return

        last_month = pd.Timestamp(dmax).strftime("%B")
        prev_month = (pd.Timestamp(dmax) - pd.DateOffset(months=1)).strftime("%B")
        if not log:
            suggestions = [
                f"Why was {last_month} slower than {prev_month}?",
                f"Top 10 items in {last_month}",
                "Flag unusual days in the last 90 days",
                "Why were there refunds this year?",
                f"Average ticket by weekday in {last_month}",
                "Net sales by month this year",
            ]
            cols = st.columns(3)
            for i, s in enumerate(suggestions):
                if cols[i % 3].button(s, key=f"sug_{i}", type="secondary", width="stretch"):
                    ask_from_anywhere(s)
        else:
            i = len(log) - 1
            _render_answer(log[i][1], log[i][2], i)
            if len(log) > 1:
                with st.expander(f"Earlier questions ({len(log) - 1})"):
                    for j in range(len(log) - 2, -1, -1):
                        _render_answer(log[j][1], log[j][2], j)

        c1, c2, c3 = st.columns([6, 1.1, 1.1], vertical_alignment="center")
        with c1:
            q = st.chat_input(f"Ask a question, e.g. why was {last_month} slow?", key="analyst_input")
        if log:
            if c2.button("Clear", key="analyst_clear", type="secondary", width="stretch"):
                st.session_state.analyst_log = []
                st.rerun()
            c3.download_button("Log", pd.DataFrame([{"Asked": t, "Question": qq, "Calls": len(a.calls)}
                                                    for t, qq, a in log]).to_csv(index=False).encode(),
                               "analyst_log.csv", "text/csv", key="analyst_dl", width="stretch",
                               icon=":material/download:")
        if q:
            _answer(q, m, ctx, dmin, dmax)
            st.rerun()


def _answer(q: str, m: Metrics, ctx: Ctx, dmin, dmax) -> None:
    log = st.session_state.analyst_log
    hist = []
    for _, pq, pa in log[-3:]:
        hist += [{"role": "user", "content": pq}, {"role": "assistant", "content": pa.text}]
    with st.spinner("Running approved metrics…"):
        try:
            ans = ask(q, m, Period(ctx.start, ctx.end, ctx.range_label()), dmin, dmax, ctx.window, hist)
        except Exception as e:  # noqa: BLE001
            ans = Answer(f"I couldn't answer that with the approved metrics ({e}). Try naming a month, a metric "
                         f"(sales, transactions, tips, refunds) or a breakdown (by item, by daypart).")
    log.append((datetime.now().strftime("%Y-%m-%d %H:%M"), q, ans))
