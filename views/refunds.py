from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import theme as T
from core.data import DAYPARTS, Ctx, filter_range


def render(ctx: Ctx) -> None:
    T.page_header("Refunds", ctx.range_label())
    if not ctx.has_tx:
        st.info("Upload transaction exports to see refunds.")
        return

    tx = ctx.tx
    pay = tx[tx["Event Type"].eq("Payment")]
    ref = tx[tx["Event Type"].eq("Refund")].copy()
    ref["Amount"] = -ref["Net Sales"]
    ref["Reason"] = ref["Refund Reason"].replace("", "(no reason)")

    ps, pe = ctx.prior_range()
    prior = filter_range(ctx.tx_all, ps, pe)
    p_ref = prior[prior["Event Type"].eq("Refund")]
    amt, p_amt = ref["Amount"].sum(), -p_ref["Net Sales"].sum()
    gross = pay["Net Sales"].sum()

    # Link refunds back to the original payment via Payment ID
    orig = ctx.tx_all[ctx.tx_all["Event Type"].eq("Payment")][["Payment ID", "Day", "Time", "Net Sales", "Staff Name"]]
    orig = orig.rename(columns={"Day": "Paid on", "Time": "Paid at", "Net Sales": "Original", "Staff Name": "Staff"})
    linked = ref.merge(orig, on="Payment ID", how="left")
    linked["Days to refund"] = (linked["Day"] - linked["Paid on"]).dt.days
    match_rate = linked["Paid on"].notna().mean() if len(linked) else 0
    partial = (tx["Partial Refunds"] != 0).sum()

    T.tiles([
        T.tile("Refunded", T.money(amt, 2), f"{T.pct(amt, p_amt):+.0f}% vs prior" if p_amt else None,
               (amt <= p_amt) if p_amt else None),
        T.tile("Refunds", f"{len(ref):,}", f"{len(p_ref):,} in prior period"),
        T.tile("Refund rate", f"{amt / gross * 100:.2f}%" if gross else "–", "of net sales"),
        T.tile("Same-day refunds", f"{(linked['Days to refund'] == 0).mean() * 100:.0f}%" if len(linked) else "–",
               "likely ring-up mistakes"),
        T.tile("Matched to payment", f"{match_rate * 100:.0f}%", f"{partial} partial refunds"),
    ])
    st.markdown("")
    if ref.empty:
        with st.container(key="card_norefunds"):
            T.card_header("No refunds in this period", "Try a longer period from the sidebar.")
        return

    a, b = st.columns([1.5, 1], gap="medium")
    with a, st.container(key="card_refmonth"):
        T.card_header("Refunds over time", "Monthly amount refunded and count")
        all_ref = ctx.tx_all[ctx.tx_all["Event Type"].eq("Refund")]
        all_ref = filter_range(all_ref, ctx.start, ctx.end)
        m = all_ref.groupby(all_ref["Day"].dt.to_period("M").dt.start_time).agg(
            Amount=("Net Sales", lambda s: -s.sum()), Count=("Net Sales", "size"))
        fig = go.Figure()
        lbl = m.index.strftime("%b %Y")
        fig.add_bar(x=lbl, y=m["Amount"], name="Amount", marker=dict(color=T.INDIGO, cornerradius=4),
                    hovertemplate="%{x}: %{y:$,.2f}<extra></extra>")
        fig.add_scatter(x=lbl, y=m["Count"], name="Count", yaxis="y2", mode="lines+markers",
                        line=dict(color=T.ORANGE, width=2.2),
                        marker=dict(size=7, color="#fff", line=dict(color=T.ORANGE, width=2)))
        fig.update_layout(yaxis=dict(tickprefix="$"),
                          yaxis2=dict(overlaying="y", side="right", showgrid=False, rangemode="tozero", tickformat="d",
                                      tickfont=dict(color=T.MUTED, size=10)))
        T.chart(fig, 300, key="ref_m")

    with b, st.container(key="card_refreason"):
        T.card_header("Why refunds happen", "By reason, amount refunded")
        r = ref.groupby("Reason").agg(Count=("Amount", "size"), Amount=("Amount", "sum")).sort_values("Amount",
                                                                                                    ascending=False)
        top = r.head(6)
        st.markdown(T.progress_bars([(k, v["Amount"] / top["Amount"].max(), f"{T.money(v['Amount'], 0)} · {int(v['Count'])}")
                                     for k, v in top.iterrows()]), unsafe_allow_html=True)

    a, b = st.columns([1, 1.5], gap="medium")
    with a, st.container(key="card_refwhen"):
        T.card_header("When refunds happen", "Count by daypart, selected period")
        dp = ref["Daypart"].value_counts().reindex(DAYPARTS).fillna(0)
        fig = go.Figure(go.Bar(x=dp.index, y=dp.values, marker=dict(color=[T.INDIGO, T.LAVENDER, T.ORANGE, T.PEACH],
                                                                       cornerradius=5),
                               hovertemplate="%{x}: %{y} refunds<extra></extra>"))
        fig.update_yaxes(tickformat="d")
        T.chart(fig, 260, key="ref_when")
    with b, st.container(key="card_reftable"):
        T.card_header("Refund log", "Each refund linked to its original payment")
        show = linked.sort_values("Day", ascending=False)[
            ["Day", "Time", "Amount", "Reason", "Original", "Paid on", "Days to refund", "Staff", "Payment ID"]]
        st.dataframe(show, hide_index=True, width="stretch", height=260, column_config={
            "Day": st.column_config.DateColumn("Refunded"), "Paid on": st.column_config.DateColumn(),
            "Amount": st.column_config.NumberColumn(format="$%.2f"),
            "Original": st.column_config.NumberColumn(format="$%.2f")})
