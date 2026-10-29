from __future__ import annotations

import calendar

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import theme as T
from core.data import Ctx, WEEKDAYS, filter_range
from core.expenses import book, daily_allocation
from views import analyst


def _calendar_html(daily: pd.DataFrame, year: int, month: int) -> str:
    cal = calendar.Calendar(firstweekday=6)  # Sunday first, like the mock
    s = daily["Net Sales"]
    m = s[(s.index.year == year) & (s.index.month == month)]
    open_days = m[m > 0]
    best = open_days.idxmax() if not open_days.empty else None
    worst = open_days.idxmin() if len(open_days) > 1 else None
    vmax = open_days.max() if not open_days.empty else 1
    rows = []
    for week in cal.monthdayscalendar(year, month):
        cells = []
        for d in week:
            if d == 0:
                cells.append("<td></td>")
                continue
            ts = pd.Timestamp(year, month, d)
            v = m.get(ts, np.nan)
            cls = "d"
            if best is not None and ts == best:
                cls += " best"
            elif worst is not None and ts == worst:
                cls += " worst"
            elif pd.isna(v) or v <= 0:
                cls += " closed"
            bar = (f'<div class="bar" style="opacity:{0.25 + 0.75 * v / vmax:.2f}"></div>'
                   if pd.notna(v) and v > 0 else "")
            tip = f"{ts:%a %b %-d}: ${v:,.0f}" if pd.notna(v) else f"{ts:%a %b %-d}: no data"
            cells.append(f'<td title="{tip}"><span class="{cls}">{d}</span>{bar}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    head = "".join(f"<th>{d}</th>" for d in ["sun", "mon", "tue", "wed", "thu", "fri", "sat"])
    legend = ""
    if best is not None:
        legend = (f'<div class="legend" style="justify-content:center;margin-top:4px">'
                  f'<span><i style="background:{T.ORANGE}"></i>Best ${open_days.max():,.0f}</span>'
                  + (f'<span><i style="background:{T.INDIGO}"></i>Slowest ${open_days.min():,.0f}</span>' if worst is not None else "")
                  + "</div>")
    return f'<table class="cal"><tr>{head}</tr>{"".join(rows)}</table>{legend}'


def render(ctx: Ctx) -> None:
    T.page_header("Overview", ctx.range_label())
    if not ctx.has_tx:
        st.info("Upload transaction exports in the sidebar to see the overview.")
        return

    d = ctx.daily
    ps, pe = ctx.prior_range()
    prior = filter_range(ctx.daily_all, ps, pe)
    ly_s, ly_e = (pd.Timestamp(ctx.start) - pd.DateOffset(years=1)), (pd.Timestamp(ctx.end) - pd.DateOffset(years=1))
    last_year = filter_range(ctx.daily_all, ly_s.date(), ly_e.date())

    net, txns = d["Net Sales"].sum(), d["Transactions"].sum()
    p_net, p_txns = prior["Net Sales"].sum(), prior["Transactions"].sum()
    exp = daily_allocation(book(), ctx.start, ctx.end)
    exp_total = float(exp.values.sum()) if not exp.empty else 0.0
    profit = net - d["Processing Fees"].sum() - exp_total

    left, mid, right = st.columns([2.15, 1.05, 1.0], gap="medium")

    # ---------------- left column ----------------
    with left:
        a, b = st.columns(2, gap="medium")
        with a, st.container(key="card_kpi", height=330):
            T.card_header("Sales summary", f"vs prior {len(d)} days", pill=f"{len(d)}d")
            st.markdown(
                T.kpi_block(T.money(net), T.pct(net, p_net), "net sales, refunds netted")
                + T.kpi_block(f"{int(txns):,}", T.pct(txns, p_txns), "transactions")
                + (T.kpi_block(T.money(profit), None, f"est. profit after ${exp_total:,.0f} expenses + fees")
                   if exp_total > 0 else
                   T.kpi_block(T.money(net / txns, 2) if txns else "–",
                               T.pct(net / txns if txns else 0, p_net / p_txns if p_txns else 0), "average ticket")),
                unsafe_allow_html=True)
        with b, st.container(key="card_cal", height=330):
            months = pd.period_range(pd.Timestamp(ctx.start), pd.Timestamp(ctx.end), freq="M")
            if "cal_i" not in st.session_state or st.session_state.cal_i >= len(months):
                st.session_state.cal_i = len(months) - 1
            c1, c2, c3 = st.columns([1, 4, 1], vertical_alignment="center")
            if c1.button("‹", key="cal_prev", type="secondary", disabled=st.session_state.cal_i <= 0):
                st.session_state.cal_i -= 1
                st.rerun()
            if c3.button("›", key="cal_next", type="secondary", disabled=st.session_state.cal_i >= len(months) - 1):
                st.session_state.cal_i += 1
                st.rerun()
            pm = months[st.session_state.cal_i]
            c2.markdown(f'<div class="cal-head">{pm.strftime("%B %Y")}</div>', unsafe_allow_html=True)
            st.markdown(_calendar_html(ctx.daily_all, pm.year, pm.month), unsafe_allow_html=True)

        with st.container(key="card_trend"):
            T.card_header("Net sales trend", f"{ctx.window}-day rolling average, against the same days last year",
                          pill=f"{ctx.window}-day")
            fig = go.Figure()
            roll = d["Net Sales"].rolling(ctx.window, min_periods=1).mean()
            fig.add_scatter(x=d.index, y=roll, name="This period", mode="lines",
                            line=dict(color=T.INDIGO, width=2.6, shape="spline", smoothing=0.8),
                            fill="tozeroy", fillcolor=T.rgba(T.INDIGO, 0.10))
            if not last_year.empty:
                ly = last_year["Net Sales"].rolling(ctx.window, min_periods=1).mean()
                ly.index = ly.index + pd.DateOffset(years=1)
                fig.add_scatter(x=ly.index, y=ly.values, name="Same days last year", mode="lines",
                                line=dict(color=T.ORANGE, width=2.2, shape="spline", smoothing=0.8))
            if exp_total > 0:
                fig.add_scatter(x=exp.index, y=exp.sum(axis=1).rolling(ctx.window, min_periods=1).mean(),
                                name="Expenses (allocated)", mode="lines",
                                line=dict(color=T.LAVENDER, width=1.8, dash="dot"))
            fig.add_scatter(x=[roll.index[-1]], y=[roll.iloc[-1]], mode="markers", showlegend=False,
                            marker=dict(size=10, color="#fff", line=dict(color=T.INDIGO, width=2.5)),
                            hovertemplate="%{y:$,.0f}<extra></extra>")
            fig.update_yaxes(tickprefix="$")
            fig.update_layout(hovermode="x unified")
            T.chart(fig, 270, key="ov_trend")

        a, b = st.columns(2, gap="medium")
        with a, st.container(key="card_catmonth"):
            T.card_header("Category mix by month", "Net sales, last 4 months in range")
            if ctx.has_items:
                it = ctx.items.assign(M=ctx.items["Day"].dt.to_period("M").dt.start_time)
                months4 = sorted(it["M"].unique())[-4:]
                it = it[it["M"].isin(months4)]
                top = it.groupby("Category")["Net Sales"].sum().nlargest(4).index
                it = it.assign(Cat=it["Category"].where(it["Category"].isin(top), "Other"))
                pv = it.pivot_table(index="M", columns="Cat", values="Net Sales", aggfunc="sum").fillna(0)
                fig = go.Figure()
                cols = [T.INDIGO, T.LAVENDER, T.ORANGE, T.PEACH, T.NEUTRAL]
                for i, c in enumerate([*top, "Other"]):
                    if c in pv:
                        fig.add_bar(y=pv.index.strftime("%b").str.upper(), x=pv[c], name=c, orientation="h",
                                    marker=dict(color=cols[i % 5], cornerradius=4),
                                    hovertemplate=f"{c}: %{{x:$,.0f}}<extra></extra>")
                fig.update_layout(barmode="stack", bargap=0.45, legend=dict(y=-0.08, font=dict(size=9)))
                fig.update_xaxes(showticklabels=False, showgrid=False)
                fig.update_yaxes(showgrid=False, autorange="reversed")
                T.chart(fig, 250, key="ov_catm")
            else:
                st.caption("Upload item exports to see category mix.")
        with b, st.container(key="card_weekday"):
            T.card_header("Sales by weekday", "Average per open day, this period vs prior")
            def wd(df):
                o = df[df["Transactions"] > 0]
                return o.groupby(o.index.day_name())["Net Sales"].mean().reindex(WEEKDAYS)
            fig = go.Figure()
            fig.add_bar(x=[w[:3] for w in WEEKDAYS], y=wd(d), name="This period",
                        marker=dict(color=T.ORANGE, cornerradius=3))
            if not prior.empty:
                fig.add_bar(x=[w[:3] for w in WEEKDAYS], y=wd(prior), name="Prior period",
                            marker=dict(color=T.PEACH, cornerradius=3))
            fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.12, legend=dict(y=-0.2))
            fig.update_yaxes(tickprefix="$")
            T.chart(fig, 250, key="ov_wd")

    # ---------------- middle column ----------------
    with mid:
        with st.container(key="card_cats"):
            T.card_header("Top categories", "Share of item net sales")
            if ctx.has_items:
                c = ctx.items.groupby(ctx.items["Category"].replace("", "(none)"))["Net Sales"].sum()
                c = c[c > 0].sort_values(ascending=False)
                tot = c.sum()
                rows = [(k, v / c.iloc[0], f"{v / tot * 100:.0f}%") for k, v in c.head(4).items()]
                st.markdown(T.progress_bars(rows), unsafe_allow_html=True)
            else:
                st.caption("Upload item exports.")

        with st.container(key="card_gauge"):
            ly_net = last_year["Net Sales"].sum()
            if ly_net > 0:
                ratio = net / ly_net
                title, sub = "Pace vs last year", f"Net sales as a share of the same days in {ly_s.year}"
                caption = (f"{T.money(net)} this period against {T.money(ly_net)} last year — "
                           f"{'ahead' if ratio >= 1 else 'behind'} by {T.money(abs(net - ly_net))}.")
            else:
                ratio = net / p_net if p_net else 0
                title, sub = "Pace vs prior period", "Net sales as a share of the prior period"
                caption = f"{T.money(net)} this period against {T.money(p_net)} in the prior period."
            T.card_header(title, sub)
            shown = min(ratio, 1.0)
            fig = go.Figure(go.Pie(values=[shown, 1 - shown], hole=0.82, sort=False, direction="clockwise",
                                   marker=dict(colors=[T.INDIGO, T.LAVENDER_SOFT]), textinfo="none",
                                   hoverinfo="skip"))
            fig.add_annotation(text=f"{ratio * 100:.1f}%" if abs(ratio - 1) < 0.01 else f"{ratio * 100:.0f}%", showarrow=False, font=dict(size=30, color=T.INK))
            fig.update_layout(showlegend=False, margin=dict(l=20, r=20, t=6, b=6))
            T.chart(fig, 210, key="ov_gauge")
            st.markdown(f'<p class="card-sub" style="text-align:center">{T.esc(caption)}</p>', unsafe_allow_html=True)
            if st.button("Ask why", width="stretch", key="ov_askwhy"):
                ly_end = pd.Timestamp(ctx.end) - pd.DateOffset(years=1)
                analyst.ask_from_anywhere(f"Why were net sales {'up' if ratio >= 1 else 'down'} "
                                          f"in {ctx.end:%B %Y} vs {ly_end:%B %Y}?" if ly_net > 0 else
                                          f"Why was {ctx.end:%B %Y} different from the month before?")

        with st.container(key="card_hours"):
            T.card_header("Busiest hours", "Net sales by hour of day")
            hr = ctx.tx.dropna(subset=["Hour"]).groupby("Hour")["Net Sales"].sum()
            hr = hr[hr > 0]
            fig = go.Figure()
            colors = [T.ORANGE if v == hr.max() else (T.PEACH if i % 2 else T.INDIGO) for i, v in enumerate(hr.values)]
            fig.add_bar(x=[f"{int(h) % 12 or 12}{'a' if h < 12 else 'p'}" for h in hr.index], y=hr.values,
                        marker=dict(color=colors, cornerradius=3), hovertemplate="%{x}: %{y:$,.0f}<extra></extra>")
            fig.update_yaxes(tickprefix="$", showgrid=True)
            fig.update_layout(bargap=0.45)
            T.chart(fig, 200, key="ov_hours")

    # ---------------- right column ----------------
    with right:
        with st.container(key="card_search"):
            def _ask():
                if st.session_state.ov_q.strip():
                    # callbacks run before the script, so the analyst panel at the top picks this up
                    st.session_state.pending_q = st.session_state.ov_q.strip()
                    st.session_state.analyst_open = True
                st.session_state.ov_q = ""
            st.text_input("Ask", placeholder="🔍  Ask the analyst… e.g. why was August slow?",
                          label_visibility="collapsed", key="ov_q", on_change=_ask)

        with st.container(key="card_yoy"):
            T.card_header("Monthly net sales", "This year and last year")
            mon = ctx.daily_all["Net Sales"].resample("MS").sum()
            y1 = pd.Timestamp(ctx.end).year
            fig = go.Figure()
            for y, col, fillc in [(y1, T.INDIGO, T.rgba(T.INDIGO, .18)), (y1 - 1, T.ORANGE, T.rgba(T.ORANGE, .18))]:
                s = mon[mon.index.year == y]
                if s.empty:
                    continue
                fig.add_scatter(x=s.index.month, y=s.values, name=str(y), mode="lines",
                                line=dict(color=col, width=2, shape="spline"), fill="tozeroy", fillcolor=fillc,
                                hovertemplate=f"{y} %{{x}}: %{{y:$,.0f}}<extra></extra>")
            fig.update_xaxes(tickvals=list(range(1, 13)), ticktext=[m[0] for m in calendar.month_abbr[1:]],
                             range=[0.8, 12.2])
            fig.update_yaxes(showticklabels=False, showgrid=False)
            fig.update_layout(legend=dict(y=-0.25))
            T.chart(fig, 200, key="ov_yoy")

        with st.container(key="card_dining"):
            T.card_header("Dining option", "Share of payments")
            pay = ctx.tx[ctx.tx["Event Type"].eq("Payment")]
            opt = pay["Dining Option"].replace({"": "Not set", "For Here, To Go": "Mixed", "To Go, For Here": "Mixed"})
            vc = opt.value_counts()
            main = vc[vc / vc.sum() >= 0.03]
            parts = list(main.items()) + ([("Other", int(vc.sum() - main.sum()))] if vc.sum() > main.sum() else [])
            st.markdown(T.segmented(parts), unsafe_allow_html=True)

        with st.container(key="card_tender"):
            T.card_header("Payment method", "Share of amount collected")
            card_amt = pay["Card"].clip(lower=0).sum() if "Card" in pay else 0
            cash_amt = pay["Cash"].clip(lower=0).sum() if "Cash" in pay else 0
            other = sum(pay[c].clip(lower=0).sum() for c in ["Square Gift Card", "Other Tender", "Cash App"] if c in pay)
            vals = [("Card", card_amt), ("Cash", cash_amt), ("Other", other)]
            vals = [(k, v) for k, v in vals if v > 0]
            tot = sum(v for _, v in vals) or 1
            fig = go.Figure(go.Pie(labels=[k for k, _ in vals], values=[v for _, v in vals], hole=0.62, sort=False,
                                   marker=dict(colors=[T.ORANGE, T.INDIGO, T.LAVENDER], line=dict(color="#fff", width=3)),
                                   textinfo="none", hovertemplate="%{label}: %{value:$,.0f} (%{percent})<extra></extra>"))
            if vals:
                fig.add_annotation(text=f"<b>{vals[0][1] / tot * 100:.0f}%</b><br><span style='font-size:11px;color:{T.MUTED}'>{vals[0][0]}</span>",
                                   showarrow=False, font=dict(size=20, color=T.INK))
            fig.update_layout(legend=dict(y=-0.08), margin=dict(l=10, r=10, t=4, b=4))
            T.chart(fig, 230, key="ov_tender")
