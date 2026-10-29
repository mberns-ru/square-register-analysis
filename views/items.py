from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import theme as T
from core.data import Ctx


def _cost_table(categories: list[str]) -> pd.DataFrame:
    if "cat_cost" not in st.session_state:
        st.session_state.cat_cost = pd.DataFrame({"Category": categories, "Cost %": [30.0] * len(categories)})
    cc = st.session_state.cat_cost
    missing = [c for c in categories if c not in set(cc["Category"])]
    if missing:
        cc = pd.concat([cc, pd.DataFrame({"Category": missing, "Cost %": [30.0] * len(missing)})], ignore_index=True)
        st.session_state.cat_cost = cc
    return cc


def render(ctx: Ctx) -> None:
    T.page_header("Item performance", ctx.range_label())
    if not ctx.has_items:
        st.info("Upload item exports in the sidebar to see item performance.")
        return

    it = ctx.items.assign(Category=ctx.items["Category"].replace("", "(none)"))
    cats = sorted(it["Category"].unique())
    cost = _cost_table(cats)
    cost_map = dict(zip(cost["Category"], cost["Cost %"].fillna(30.0) / 100))

    tbl = it.groupby(["Item"]).agg(Category=("Category", lambda s: s.mode().iat[0]), Units=("Qty", "sum"),
                                   Gross=("Gross Sales", "sum"), Discounts=("Discounts", "sum"),
                                   Net=("Net Sales", "sum")).reset_index()
    tbl = tbl[tbl["Units"] > 0]
    tbl["Avg price"] = tbl["Net"] / tbl["Units"]
    tbl["Est. cost"] = tbl["Net"] * tbl["Category"].map(cost_map).fillna(0.3)
    tbl["Est. margin"] = tbl["Net"] - tbl["Est. cost"]
    tbl["Margin / unit"] = tbl["Est. margin"] / tbl["Units"]
    # "Sells well but earns little": top quartile by units, bottom quartile by margin per unit
    u_hi = tbl["Units"].quantile(0.75)
    m_lo = tbl.loc[tbl["Units"] >= u_hi, "Margin / unit"].quantile(0.25)
    tbl["Flag"] = (tbl["Units"] >= u_hi) & (tbl["Margin / unit"] <= m_lo)

    T.tiles([
        T.tile("Units sold", f"{tbl['Units'].sum():,.0f}"),
        T.tile("Item net sales", T.money(tbl["Net"].sum())),
        T.tile("Est. item margin", T.money(tbl["Est. margin"].sum()),
               f"{tbl['Est. margin'].sum() / tbl['Net'].sum() * 100:.0f}% of net" if tbl["Net"].sum() else None, True),
        T.tile("Distinct items", f"{len(tbl):,}"),
        T.tile("Flagged items", f"{int(tbl['Flag'].sum())}", "sell well, earn little", False),
    ])
    st.markdown("")

    left, right = st.columns([1.45, 1], gap="medium")
    with left, st.container(key="card_topitems"):
        c1, c2 = st.columns([3, 2], vertical_alignment="center")
        with c1:
            T.card_header("Top items", "Ranked over the selected period")
        by = c2.segmented_control("Rank by", ["Net", "Units", "Est. margin"], default="Net",
                                  label_visibility="collapsed", key="it_by") or "Net"
        top_n = 15
        ti = tbl.sort_values(by, ascending=False).head(top_n).iloc[::-1]
        fig = go.Figure()
        fig.add_bar(y=ti["Item"], x=ti[by], orientation="h",
                    marker=dict(color=[T.ORANGE if f else T.INDIGO for f in ti["Flag"]], cornerradius=4),
                    customdata=ti[["Units", "Net", "Est. margin"]].values,
                    hovertemplate="%{y}<br>Units %{customdata[0]:,.0f} · Net %{customdata[1]:$,.0f} · "
                                  "Margin %{customdata[2]:$,.0f}<extra></extra>")
        fig.update_layout(bargap=0.3)
        if by != "Units":
            fig.update_xaxes(tickprefix="$")
        T.chart(fig, 470, key="it_top")
        st.markdown(f'<div class="legend"><span><i style="background:{T.INDIGO}"></i>Item</span>'
                    f'<span><i style="background:{T.ORANGE}"></i>Flagged: high volume, low margin per unit</span></div>',
                    unsafe_allow_html=True)

    with right:
        with st.container(key="card_catdonut"):
            T.card_header("Category share", "Item net sales")
            cat = tbl.groupby("Category")["Net"].sum().sort_values(ascending=False)
            big = cat.head(5)
            if len(cat) > 5:
                big = pd.concat([big, pd.Series({"Other": cat.iloc[5:].sum()})])
            fig = go.Figure(go.Pie(labels=big.index, values=big.values, hole=0.6, sort=False,
                                   marker=dict(colors=T.SERIES, line=dict(color="#fff", width=3)),
                                   textinfo="none", hovertemplate="%{label}: %{value:$,.0f} (%{percent})<extra></extra>"))
            fig.add_annotation(text=f"<b>{big.iloc[0] / big.sum() * 100:.0f}%</b><br>"
                                    f"<span style='font-size:11px;color:{T.MUTED}'>{T.esc(big.index[0])}</span>",
                               showarrow=False, font=dict(size=20))
            fig.update_layout(legend=dict(orientation="v", y=0.5, x=1.02, xanchor="left", yanchor="middle"),
                              margin=dict(l=0, r=0, t=4, b=4))
            T.chart(fig, 240, key="it_cat")
        with st.container(key="card_flags"):
            T.card_header("Sells well, earns little", "Top-quartile volume, bottom-quartile margin per unit")
            fl = tbl[tbl["Flag"]].sort_values("Units", ascending=False).head(6)
            if fl.empty:
                st.caption("No items flagged with the current cost assumptions.")
            else:
                st.markdown(T.progress_bars(
                    [(r["Item"], r["Units"] / fl["Units"].max(),
                      f"{r['Units']:,.0f} units · ${r['Margin / unit']:.2f}/unit") for _, r in fl.iterrows()],
                    colors=[T.ORANGE, T.PEACH]), unsafe_allow_html=True)

    with st.container(key="card_itemtrend"):
        c1, c2 = st.columns([2, 3], vertical_alignment="center")
        with c1:
            T.card_header("Item trend", f"Daily units, {ctx.window}-day rolling average")
        default = list(tbl.sort_values("Net", ascending=False)["Item"].head(3))
        pick = c2.multiselect("Items", sorted(tbl["Item"]), default=default, label_visibility="collapsed",
                              key="it_pick")
        if pick:
            tr = it[it["Item"].isin(pick)].groupby(["Day", "Item"])["Qty"].sum().unstack(fill_value=0)
            tr = tr.reindex(pd.date_range(ctx.start, ctx.end), fill_value=0).rolling(ctx.window, min_periods=1).mean()
            fig = go.Figure()
            for i, c in enumerate(tr.columns):
                fig.add_scatter(x=tr.index, y=tr[c], name=c, mode="lines",
                                line=dict(color=T.SERIES[i % len(T.SERIES)], width=2.3, shape="spline"))
            fig.update_layout(hovermode="x unified")
            T.chart(fig, 300, key="it_trend")

    with st.container(key="card_itemtable"):
        T.card_header("Every item", "Units, sales and estimated margin. Margin uses the cost % per category below.")
        t1, t2 = st.tabs(["Items", "Cost assumptions"])
        with t1:
            show = tbl.sort_values("Net", ascending=False)[
                ["Category", "Item", "Units", "Avg price", "Net", "Discounts", "Est. margin", "Margin / unit", "Flag"]]
            st.dataframe(show, width="stretch", hide_index=True, height=380, column_config={
                "Units": st.column_config.NumberColumn(format="%d"),
                "Avg price": st.column_config.NumberColumn(format="$%.2f"),
                "Net": st.column_config.NumberColumn(format="$%.0f"),
                "Discounts": st.column_config.NumberColumn(format="$%.0f"),
                "Est. margin": st.column_config.NumberColumn(format="$%.0f"),
                "Margin / unit": st.column_config.NumberColumn(format="$%.2f"),
                "Flag": st.column_config.CheckboxColumn("Low margin flag"),
            })
        with t2:
            st.caption("Ingredient and packaging cost as a share of each category's net sales. Square exports don't "
                       "include costs, so these are estimates until ingredient costing is added.")
            edited = st.data_editor(cost, hide_index=True, width="stretch", key="cost_editor",
                                    disabled=["Category"],
                                    column_config={"Cost %": st.column_config.NumberColumn(min_value=0, max_value=100,
                                                                                           step=1, format="%.0f%%")})
            if not edited.equals(cost):
                st.session_state.cat_cost = edited
                st.rerun()
