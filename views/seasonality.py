from __future__ import annotations

import calendar

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import theme as T
from core.data import DAYPART_HOURS, DAYPARTS, WEEKDAYS, Ctx
from views.forecast import month_index


def render(ctx: Ctx) -> None:
    T.page_header("Seasonality", "Patterns by month, weekday and hour")
    if not ctx.has_tx:
        st.info("Upload transaction exports to see seasonality.")
        return

    s = ctx.daily_all["Net Sales"]
    midx = month_index(s)
    peak, low = midx.idxmax(), midx.idxmin()
    wd = ctx.daily[ctx.daily["Transactions"] > 0]
    wdm = wd.groupby(wd.index.dayofweek)["Net Sales"].mean()
    dp = ctx.tx.groupby("Daypart")["Net Sales"].sum().reindex(DAYPARTS).fillna(0)

    T.tiles([
        T.tile("Strongest month", calendar.month_name[peak], f"{(midx[peak] - 1) * 100:+.0f}% vs a typical month", True),
        T.tile("Softest month", calendar.month_name[low], f"{(midx[low] - 1) * 100:+.0f}% vs a typical month", False),
        T.tile("Best weekday", WEEKDAYS[wdm.idxmax()] if not wdm.empty else "–",
               T.money(wdm.max()) + " avg" if not wdm.empty else None),
        T.tile("Biggest daypart", dp.idxmax(), f"{dp.max() / dp.sum() * 100:.0f}% of sales · {DAYPART_HOURS[dp.idxmax()]}"),
    ])
    st.markdown("")

    a, b = st.columns([1.4, 1], gap="medium")
    with a, st.container(key="card_years"):
        T.card_header("Year over year", "Monthly net sales for each year in the data")
        mon = s.resample("MS").sum()
        last = s.index.max()
        if not last.is_month_end:  # drop a partial final month
            mon = mon.iloc[:-1]
        fig = go.Figure()
        years = sorted(mon.index.year.unique())
        cols = [T.PEACH, T.LAVENDER, T.ORANGE, T.INDIGO]
        for i, y in enumerate(years):
            m = mon[mon.index.year == y]
            c = cols[(i - len(years)) % len(cols)]
            fig.add_scatter(x=m.index.strftime("%b"), y=m.values, name=str(y), mode="lines+markers",
                            line=dict(color=c, width=2.6 if y == years[-1] else 1.8, shape="spline"),
                            marker=dict(size=6), hovertemplate=f"%{{x}} {y}: %{{y:$,.0f}}<extra></extra>")
        fig.update_xaxes(categoryorder="array", categoryarray=list(calendar.month_abbr)[1:])
        fig.update_yaxes(tickprefix="$")
        T.chart(fig, 320, key="se_years")
    with b, st.container(key="card_midx"):
        T.card_header("Seasonal index", "Each month vs the yearly average (100 = typical)")
        fig = go.Figure(go.Bar(x=[calendar.month_abbr[m] for m in midx.index], y=midx.values * 100,
                               marker=dict(color=[T.ORANGE if v >= 1 else T.INDIGO for v in midx.values],
                                           cornerradius=4),
                               hovertemplate="%{x}: %{y:.0f}<extra></extra>"))
        fig.add_hline(y=100, line=dict(color=T.MUTED, width=1, dash="dot"))
        fig.update_yaxes(range=[max(0, midx.min() * 100 - 15), midx.max() * 100 + 8])
        T.chart(fig, 320, key="se_idx")

    a, b = st.columns([1.4, 1], gap="medium")
    with a, st.container(key="card_heat"):
        T.card_header("When customers come in", "Average net sales per week, by weekday and hour (selected period)")
        t = ctx.tx.dropna(subset=["Hour"])
        weeks = max(1, (pd.Timestamp(ctx.end) - pd.Timestamp(ctx.start)).days / 7)
        g = t.groupby([t["Day"].dt.dayofweek, "Hour"])["Net Sales"].sum().unstack(fill_value=0) / weeks
        g = g.reindex(range(7)).fillna(0)
        g = g.loc[:, g.sum() > g.values.sum() * 0.002]
        fig = go.Figure(go.Heatmap(z=g.values, x=[f"{int(h) % 12 or 12}{'a' if h < 12 else 'p'}" for h in g.columns],
                                   y=[w[:3] for w in WEEKDAYS],
                                   colorscale=[[0, T.TINT], [0.45, T.LAVENDER], [0.8, T.INDIGO], [1, T.ORANGE]],
                                   showscale=False, xgap=3, ygap=3,
                                   hovertemplate="%{y} %{x}: %{z:$,.0f}/week<extra></extra>"))
        fig.update_yaxes(autorange="reversed", showgrid=False)
        T.chart(fig, 300, key="se_heat")
    with b, st.container(key="card_daypart"):
        T.card_header("Daypart mix by month", "Share of net sales")
        first = pd.Timestamp(ctx.end).to_period("M").start_time - pd.DateOffset(months=11)
        t = ctx.tx_all[(ctx.tx_all["Day"] >= first) & (ctx.tx_all["Day"] <= pd.Timestamp(ctx.end))]
        g = t.groupby([t["Day"].dt.to_period("M").dt.start_time, "Daypart"])["Net Sales"].sum().unstack(fill_value=0)
        g = g.reindex(columns=DAYPARTS).fillna(0)
        g = g.div(g.sum(axis=1), axis=0) * 100
        fig = go.Figure()
        for c, col in zip(DAYPARTS, [T.PEACH, T.ORANGE, T.INDIGO, T.LAVENDER]):
            fig.add_bar(x=g.index.strftime("%b %y"), y=g[c], name=c, marker=dict(color=col),
                        hovertemplate=f"{c} %{{x}}: %{{y:.0f}}%<extra></extra>")
        fig.update_layout(barmode="stack", bargap=0.35)
        fig.update_yaxes(ticksuffix="%", range=[0, 100])
        T.chart(fig, 300, key="se_dp")
