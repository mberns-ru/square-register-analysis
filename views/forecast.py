from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import theme as T
from core.data import DAYPARTS, WEEKDAYS, Ctx


def month_index(s: pd.Series) -> pd.Series:
    """Average seasonal index per calendar month (1..12), from complete months only."""
    m = s.resample("MS").mean()
    m = m[(m.index >= s.index.min()) & (m.index + pd.offsets.MonthEnd(0) <= s.index.max())]
    yr = m.groupby(m.index.year).transform("mean")
    idx = (m / yr).groupby(m.index.month).mean()
    return idx.reindex(range(1, 13)).fillna(1.0)


def forecast(s: pd.Series, origin: pd.Timestamp, horizon: int, weeks: int = 8) -> pd.Series:
    """Blend of (a) recent weekday medians scaled by the seasonal month index and (b) the same weekday last year
    (364 days back) scaled by recent year-over-year growth. Falls back to (a) without a year of history."""
    a = _weekday_season(s, origin, horizon, weeks)
    ly = s.reindex(a.index - pd.Timedelta(days=364))
    rec = s[(s.index > origin - pd.Timedelta(weeks=weeks)) & (s.index <= origin)]
    rec_ly = s.reindex(rec.index - pd.Timedelta(days=364))
    if ly.isna().any() or rec_ly.isna().any() or rec_ly.sum() <= 0:
        return a
    growth = rec.sum() / rec_ly.sum()
    return 0.5 * a + 0.5 * pd.Series(ly.values * growth, index=a.index)


def _weekday_season(s: pd.Series, origin: pd.Timestamp, horizon: int, weeks: int = 8) -> pd.Series:
    hist = s[s.index <= origin]
    recent = hist[hist.index > origin - pd.Timedelta(weeks=weeks)]
    level = recent.groupby(recent.index.dayofweek).median()
    midx = month_index(hist) if len(hist) > 400 else pd.Series(1.0, index=range(1, 13))
    rec_idx = midx.reindex(recent.index.month).mean()
    fut = pd.date_range(origin + pd.Timedelta(days=1), periods=horizon)
    vals = [level.get(d.dayofweek, 0) * midx[d.month] / rec_idx for d in fut]
    return pd.Series(vals, index=fut)


def backtest(s: pd.Series, horizon: int) -> tuple[float, float, pd.DataFrame]:
    errs = []
    for k in range(4):
        origin = s.index.max() - pd.Timedelta(days=horizon * (k + 1))
        if origin - s.index.min() < pd.Timedelta(days=90):
            break
        f = forecast(s, origin, horizon)
        a = s.reindex(f.index)
        errs.append(pd.DataFrame({"f": f, "a": a, "origin": origin}))
    if not errs:
        return np.nan, np.nan, pd.DataFrame()
    e = pd.concat(errs)
    e = e[e["a"] > 0]
    mape = (abs(e["f"] - e["a"]) / e["a"]).mean() * 100
    rel_sd = ((e["a"] - e["f"]) / e["f"].replace(0, np.nan)).std()
    return mape, rel_sd, e


def render(ctx: Ctx) -> None:
    T.page_header("Forecast", "Demand forecast for prep and staffing")
    if not ctx.has_tx:
        st.info("Upload transaction exports to forecast.")
        return

    s = ctx.daily_all["Net Sales"]
    origin = s.index.max()
    c1, c2 = st.columns([2.2, 1.5], vertical_alignment="bottom")
    horizon = c2.segmented_control("Horizon", [14, 30, 60, 90], default=30, format_func=lambda x: f"{x} days",
                                   key="fc_h") or 30
    f = forecast(s, origin, horizon)
    mape, rel_sd, bt = backtest(s, min(horizon, 28))
    z = 1.28  # ~80% band
    lo = (f * (1 - z * (rel_sd if pd.notna(rel_sd) else 0.15))).clip(lower=0)
    hi = f * (1 + z * (rel_sd if pd.notna(rel_sd) else 0.15))
    ly = s.reindex(f.index - pd.Timedelta(days=364))  # same weekday last year
    tx = ctx.daily_all["Transactions"]
    ft = forecast(tx, origin, horizon)

    T.tiles([
        T.tile(f"Forecast net sales, next {horizon} days", T.money(f.sum()),
               f"{T.pct(f.sum(), ly.sum()):+.1f}% vs same days last year" if ly.sum() else None,
               bool(f.sum() >= ly.sum()) if ly.sum() else None),
        T.tile("Expected transactions", f"{ft.sum():,.0f}", f"~{ft.mean():,.0f} per day"),
        T.tile("Busiest expected day", f"{f.idxmax():%a %b %-d}", T.money(f.max())),
        T.tile("Backtest error (MAPE)", f"{mape:.0f}%" if pd.notna(mape) else "–",
               "avg daily miss over the last 4 windows"),
    ])
    st.markdown("")

    with st.container(key="card_fc"):
        T.card_header("Daily net sales forecast",
                      f"From {origin + pd.Timedelta(days=1):%b %-d, %Y}. Band shows the typical miss (80%).",
                      pill="weekday × season model")
        hist = s[s.index > origin - pd.Timedelta(days=120)]
        fig = go.Figure()
        fig.add_scatter(x=hist.index, y=hist.rolling(ctx.window, min_periods=1).mean(), name=f"Actual ({ctx.window}-day avg)",
                        line=dict(color=T.INDIGO, width=2.4, shape="spline"))
        fig.add_bar(x=hist.index, y=hist, name="Actual daily", marker=dict(color=T.LAVENDER_SOFT), hoverinfo="skip")
        fig.add_scatter(x=list(f.index) + list(f.index[::-1]), y=list(hi) + list(lo[::-1]), fill="toself",
                        fillcolor="rgba(238,138,78,.16)", line=dict(width=0), name="Likely range", hoverinfo="skip")
        fig.add_scatter(x=f.index, y=f, name="Forecast", mode="lines+markers",
                        line=dict(color=T.ORANGE, width=2.4), marker=dict(size=5))
        if ly.notna().any():
            fig.add_scatter(x=f.index, y=ly.values, name="Same days last year", mode="lines",
                            line=dict(color=T.MUTED, width=1.4, dash="dot"))
        fig.update_yaxes(tickprefix="$")
        fig.update_layout(hovermode="x unified", bargap=0.2)
        T.chart(fig, 360, key="fc_main")

    a, b = st.columns([1.35, 1], gap="medium")
    with a, st.container(key="card_staff"):
        T.card_header("Next week: expected transactions", "By weekday and daypart, for staffing and prep")
        t = ctx.tx_all[ctx.tx_all["Event Type"].eq("Payment") & (ctx.tx_all["Day"] > origin - pd.Timedelta(weeks=8))]
        weeks = t["Day"].dt.to_period("W").nunique() or 1
        grid = t.groupby([t["Day"].dt.day_name(), "Daypart"]).size().unstack(fill_value=0) / weeks
        midx = month_index(tx)
        next_m = (origin + pd.Timedelta(days=4)).month
        adj = midx[next_m] / midx.reindex(t["Day"].dt.month).mean()
        grid = (grid * adj).reindex(index=WEEKDAYS, columns=DAYPARTS).fillna(0)
        fig = go.Figure(go.Heatmap(z=grid.values, x=grid.columns, y=[w[:3] for w in grid.index],
                                   colorscale=[[0, "#F3F4FD"], [0.5, T.LAVENDER], [1, T.INDIGO]],
                                   text=grid.round(0).astype(int).values, texttemplate="%{text}",
                                   textfont=dict(size=11), showscale=False, xgap=4, ygap=4,
                                   hovertemplate="%{y} %{x}: ~%{z:.0f} transactions<extra></extra>"))
        fig.update_yaxes(autorange="reversed", showgrid=False)
        T.chart(fig, 300, key="fc_heat")
    with b, st.container(key="card_prep"):
        T.card_header("Prep list: expected units next 7 days", "Top items, same weekday × season model")
        if ctx.has_items:
            it = ctx.items_all[ctx.items_all["Day"] > origin - pd.Timedelta(weeks=8)]
            top = it.groupby("Item")["Qty"].sum().nlargest(8).index
            rows = []
            for name in top:
                u = it[it["Item"] == name].groupby("Day")["Qty"].sum()
                u = u.reindex(pd.date_range(origin - pd.Timedelta(weeks=8) + pd.Timedelta(days=1), origin), fill_value=0)
                rows.append((name, forecast(u, origin, 7).sum()))
            mx = max(v for _, v in rows) or 1
            st.markdown(T.progress_bars([(n, v / mx, f"~{v:,.0f}") for n, v in rows],
                                        colors=[T.ORANGE, T.PEACH, T.INDIGO, T.LAVENDER]), unsafe_allow_html=True)
        else:
            st.caption("Upload item exports for an item-level prep list.")
    st.caption("Model: half from each weekday's median over the last 8 weeks scaled by the seasonal month index, half from "
               "the same weekday last year scaled by recent year-over-year growth. It doesn't know about holidays, events or weather yet.")
