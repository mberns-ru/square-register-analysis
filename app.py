"""
Sales & Expense Dashboard (Streamlit)

Upload Square-style monthly exports from the `transactions/` and `items/` folders,
view sales metrics with rolling averages, and enter expenses (rent, payroll, bills,
supplies, ...) to see estimated profit.

Run:
    pip install streamlit pandas plotly
    streamlit run app.py
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Sales & Expense Dashboard", page_icon="📊", layout="wide")

MONEY_COLS = [
    "Gross Sales", "Discounts", "Service Charges", "Net Sales", "Gift Card Sales",
    "Tax", "Tip", "Partial Refunds", "Total Collected", "Fees", "Net Total",
]
ITEM_MONEY_COLS = ["Gross Sales", "Discounts", "Net Sales", "Tax"]
EXPENSE_CATEGORIES = ["Rent", "Payroll", "Utilities / Bills", "Supplies", "Insurance",
                      "Marketing", "Loan / Debt", "Taxes", "Other"]
FREQUENCIES = ["Monthly", "Weekly", "Yearly", "One-time"]


# ----------------------------------------------------------------------------
# Loading / cleaning
# ----------------------------------------------------------------------------
def parse_money(series: pd.Series) -> pd.Series:
    """Convert strings like '$1,234.50', '-$3.00', '($3.00)' to floats."""
    if series.dtype.kind in "fi":
        return series.astype(float)
    s = series.astype(str).str.strip()
    neg = s.str.startswith("(") & s.str.endswith(")") | s.str.startswith("-")
    s = s.str.replace(r"[^0-9.]", "", regex=True)
    out = pd.to_numeric(s, errors="coerce").fillna(0.0)
    return out.where(~neg, -out)


@st.cache_data(show_spinner=False)
def load_files(file_blobs: tuple[tuple[str, bytes], ...], kind: str) -> pd.DataFrame:
    frames = []
    money = MONEY_COLS if kind == "transactions" else ITEM_MONEY_COLS
    for name, blob in file_blobs:
        try:
            df = pd.read_csv(io.BytesIO(blob), dtype=str, keep_default_na=False)
        except Exception as e:  # noqa: BLE001
            st.warning(f"Could not read {name}: {e}")
            continue
        df["Source File"] = name
        frames.append(df)
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    for c in money:
        if c in df.columns:
            df[c] = parse_money(df[c])
    if "Qty" in df.columns:
        df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce").fillna(0)
    if "Time" in df.columns:
        df["Hour"] = pd.to_datetime(df["Time"], format="%H:%M:%S", errors="coerce").dt.hour

    # De-duplicate in case the same month is uploaded twice.
    key = ["Payment ID"] if "Payment ID" in df.columns and kind == "transactions" else None
    if key and (df["Payment ID"] != "").any():
        df = df.drop_duplicates(subset=key + ["Event Type"] if "Event Type" in df.columns else key)
    else:
        df = df.drop_duplicates()
    return df


# ----------------------------------------------------------------------------
# Expenses
# ----------------------------------------------------------------------------
def expense_daily_series(expenses: pd.DataFrame, start: date, end: date) -> pd.Series:
    """Spread each expense across days in [start, end]."""
    idx = pd.date_range(start, end, freq="D")
    total = pd.Series(0.0, index=idx)
    if expenses is None or expenses.empty:
        return total

    for _, r in expenses.iterrows():
        amt = r.get("Amount")
        freq = r.get("Frequency")
        if pd.isna(amt) or not amt or freq not in FREQUENCIES:
            continue
        s = pd.to_datetime(r.get("Start Date"), errors="coerce")
        e = pd.to_datetime(r.get("End Date"), errors="coerce")

        if freq == "One-time":
            if pd.notna(s) and s in total.index:
                total.loc[s] += float(amt)
            continue

        per_day = {"Monthly": amt * 12 / 365, "Weekly": amt / 7, "Yearly": amt / 365}[freq]
        mask = pd.Series(True, index=idx)
        if pd.notna(s):
            mask &= idx >= s
        if pd.notna(e):
            mask &= idx <= e
        total[mask] += float(per_day)
    return total


# ----------------------------------------------------------------------------
# Sidebar: uploads
# ----------------------------------------------------------------------------
st.title("📊 Sales & Expense Dashboard")

with st.sidebar:
    st.header("1. Upload data")
    tx_files = st.file_uploader(
        "Transaction CSVs (from `transactions/` folder)", type="csv", accept_multiple_files=True, key="tx"
    )
    item_files = st.file_uploader(
        "Item CSVs (from `items/` folder)", type="csv", accept_multiple_files=True, key="items"
    )
    st.caption("Tip: select all files in the folder at once (Ctrl/Cmd+A in the file dialog).")

tx = load_files(tuple((f.name, f.getvalue()) for f in tx_files), "transactions") if tx_files else pd.DataFrame()
items = load_files(tuple((f.name, f.getvalue()) for f in item_files), "items") if item_files else pd.DataFrame()

if tx.empty and items.empty:
    st.info("Upload transaction and/or item CSV files in the sidebar to get started.")
    st.stop()

# ----------------------------------------------------------------------------
# Sidebar: filters
# ----------------------------------------------------------------------------
base = tx if not tx.empty else items
min_d, max_d = base["Date"].min().date(), base["Date"].max().date()

with st.sidebar:
    st.header("2. Filters")
    date_range = st.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:
        start, end = min_d, max_d

    loc_source = base["Location"] if "Location" in base.columns else pd.Series(dtype=str)
    locations = sorted([l for l in loc_source.unique() if l])
    sel_locs = st.multiselect("Location", locations, default=locations) if len(locations) > 1 else locations

    window = st.select_slider("Rolling average window (days)", options=[3, 7, 14, 28, 30, 60, 90], value=7)
    metric_choice = st.selectbox("Metric to chart", ["Net Sales", "Gross Sales", "Transactions", "Tips", "Avg Ticket"])


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df[(df["Date"].dt.date >= start) & (df["Date"].dt.date <= end)]
    if sel_locs and "Location" in out.columns and len(locations) > 1:
        out = out[out["Location"].isin(sel_locs)]
    return out


tx_f, items_f = apply_filters(tx), apply_filters(items)

# ----------------------------------------------------------------------------
# Daily aggregation
# ----------------------------------------------------------------------------
full_idx = pd.date_range(start, end, freq="D")

if not tx_f.empty:
    pay = tx_f.copy()
    is_payment = pay["Event Type"].eq("Payment") if "Event Type" in pay.columns else pd.Series(True, index=pay.index)
    daily = pay.groupby(pay["Date"].dt.normalize()).agg(
        **{
            "Gross Sales": ("Gross Sales", "sum"),
            "Net Sales": ("Net Sales", "sum"),
            "Tips": ("Tip", "sum"),
            "Tax": ("Tax", "sum"),
            "Fees": ("Fees", "sum"),
            "Total Collected": ("Total Collected", "sum"),
        }
    )
    daily["Transactions"] = is_payment.groupby(pay["Date"].dt.normalize()).sum()
    daily = daily.reindex(full_idx, fill_value=0)
    daily["Processing Fees"] = -daily["Fees"]  # Square exports fees as negatives
    daily["Avg Ticket"] = (daily["Net Sales"] / daily["Transactions"]).where(daily["Transactions"] > 0)
else:
    daily = pd.DataFrame(index=full_idx)

tab_overview, tab_items, tab_expenses, tab_pl, tab_data = st.tabs(
    ["Overview", "Items", "Expenses", "Profit & Loss", "Data"]
)

# ----------------------------------------------------------------------------
# Overview
# ----------------------------------------------------------------------------
with tab_overview:
    if tx_f.empty:
        st.info("Upload transaction files to see sales metrics.")
    else:
        n_days = len(full_idx)
        open_days = int((daily["Transactions"] > 0).sum())
        net, gross = daily["Net Sales"].sum(), daily["Gross Sales"].sum()
        txns = int(daily["Transactions"].sum())

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Net sales", f"${net:,.0f}")
        c2.metric("Gross sales", f"${gross:,.0f}")
        c3.metric("Transactions", f"{txns:,}")
        c4.metric("Avg ticket", f"${net / txns:,.2f}" if txns else "–")
        c5.metric("Avg / open day", f"${net / open_days:,.0f}" if open_days else "–")

        c6, c7, c8, c9, c10 = st.columns(5)
        c6.metric("Tips", f"${daily['Tips'].sum():,.0f}")
        c7.metric("Discounts", f"${-tx_f['Discounts'].abs().sum():,.0f}")
        c8.metric("Processing fees", f"${daily['Processing Fees'].sum():,.0f}")
        c9.metric("Days with sales", f"{open_days} / {n_days}")
        # Period-over-period: compare last `window` days vs prior `window` days
        if n_days >= 2 * window:
            cur = daily["Net Sales"].iloc[-window:].sum()
            prev = daily["Net Sales"].iloc[-2 * window:-window].sum()
            delta = (cur - prev) / prev * 100 if prev else None
            c10.metric(f"Last {window}d net", f"${cur:,.0f}", f"{delta:+.1f}% vs prior" if delta is not None else None)
        else:
            c10.metric(f"Last {window}d net", f"${daily['Net Sales'].iloc[-window:].sum():,.0f}")

        st.subheader(f"{metric_choice} – daily with {window}-day rolling average")
        series = daily[metric_choice] if metric_choice != "Avg Ticket" else daily["Avg Ticket"]
        # Rolling avg: ignore closed days (0 txns) for ticket; otherwise include zero days
        rolling = series.rolling(window, min_periods=max(1, window // 2)).mean()

        fig = go.Figure()
        fig.add_bar(x=daily.index, y=series, name="Daily", opacity=0.45)
        fig.add_scatter(x=daily.index, y=rolling, name=f"{window}-day avg", line=dict(width=3))
        fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)

        left, right = st.columns(2)
        with left:
            st.subheader("Monthly net sales")
            monthly = daily["Net Sales"].resample("MS").sum().reset_index()
            monthly.columns = ["Month", "Net Sales"]
            f = px.bar(monthly, x="Month", y="Net Sales")
            f.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(f, use_container_width=True)
        with right:
            st.subheader("Avg net sales by weekday")
            wd = daily.assign(Weekday=daily.index.day_name())
            wd = wd[wd["Transactions"] > 0].groupby("Weekday")["Net Sales"].mean()
            order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            wd = wd.reindex([d for d in order if d in wd.index]).reset_index()
            f = px.bar(wd, x="Weekday", y="Net Sales")
            f.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(f, use_container_width=True)

        if "Hour" in tx_f.columns:
            st.subheader("Net sales by hour of day")
            hr = tx_f.dropna(subset=["Hour"]).groupby("Hour")["Net Sales"].sum().reset_index()
            f = px.bar(hr, x="Hour", y="Net Sales")
            f.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), xaxis=dict(dtick=1))
            st.plotly_chart(f, use_container_width=True)

# ----------------------------------------------------------------------------
# Items
# ----------------------------------------------------------------------------
with tab_items:
    if items_f.empty:
        st.info("Upload item files to see item metrics.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Units sold", f"{items_f['Qty'].sum():,.0f}")
        c2.metric("Item net sales", f"${items_f['Net Sales'].sum():,.0f}")
        c3.metric("Distinct items", f"{items_f['Item'].nunique():,}")

        top_n = st.slider("Top N", 5, 30, 15)
        by = st.radio("Rank by", ["Net Sales", "Qty"], horizontal=True)

        left, right = st.columns(2)
        with left:
            st.subheader("Top items")
            ti = items_f.groupby("Item").agg(Qty=("Qty", "sum"), **{"Net Sales": ("Net Sales", "sum")})
            ti = ti.sort_values(by, ascending=False).head(top_n).reset_index()
            f = px.bar(ti.iloc[::-1], x=by, y="Item", orientation="h")
            f.update_layout(height=max(320, 24 * top_n), margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(f, use_container_width=True)
        with right:
            st.subheader("By category")
            cat = items_f.assign(Category=items_f["Category"].replace("", "(none)"))
            cat = cat.groupby("Category").agg(Qty=("Qty", "sum"), **{"Net Sales": ("Net Sales", "sum")}).reset_index()
            f = px.pie(cat, names="Category", values="Net Sales", hole=0.4)
            f.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(f, use_container_width=True)

        st.subheader("Item trend")
        pick = st.multiselect("Items", sorted(items_f["Item"].unique()),
                              default=list(ti["Item"].head(3)) if not ti.empty else [])
        if pick:
            tr = items_f[items_f["Item"].isin(pick)]
            tr = tr.groupby([tr["Date"].dt.normalize(), "Item"])[by].sum().unstack(fill_value=0)
            tr = tr.reindex(full_idx, fill_value=0).rolling(window, min_periods=1).mean()
            f = px.line(tr, labels={"value": f"{by} ({window}-day avg)", "index": "Date"})
            f.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(f, use_container_width=True)

        st.subheader("Item table")
        tbl = items_f.groupby(["Category", "Item"]).agg(
            Qty=("Qty", "sum"), Gross=("Gross Sales", "sum"), Discounts=("Discounts", "sum"), Net=("Net Sales", "sum")
        ).reset_index().sort_values("Net", ascending=False)
        st.dataframe(tbl, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# Expenses (manual input)
# ----------------------------------------------------------------------------
with tab_expenses:
    st.subheader("Enter expenses")
    st.caption(
        "Recurring expenses (Monthly / Weekly / Yearly) are spread evenly across days between Start and End "
        "(leave blank for open-ended). One-time expenses hit on the Start Date."
    )

    if "expenses" not in st.session_state:
        st.session_state.expenses = pd.DataFrame(
            {
                "Category": ["Rent", "Payroll", "Utilities / Bills", "Supplies"],
                "Description": ["", "", "", ""],
                "Amount": [0.0, 0.0, 0.0, 0.0],
                "Frequency": ["Monthly", "Monthly", "Monthly", "Monthly"],
                "Start Date": [min_d] * 4,
                "End Date": [None] * 4,
            }
        )

    up = st.file_uploader("Load saved expenses (CSV)", type="csv", key="exp_up")
    if up is not None and st.session_state.get("_exp_loaded") != up.name:
        try:
            loaded = pd.read_csv(up)
            for c in ("Start Date", "End Date"):
                loaded[c] = pd.to_datetime(loaded[c], errors="coerce").dt.date
            st.session_state.expenses = loaded[["Category", "Description", "Amount", "Frequency", "Start Date", "End Date"]]
            st.session_state._exp_loaded = up.name
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not load expenses: {e}")

    edited = st.data_editor(
        st.session_state.expenses,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Category": st.column_config.SelectboxColumn(options=EXPENSE_CATEGORIES, required=True),
            "Description": st.column_config.TextColumn(),
            "Amount": st.column_config.NumberColumn(format="$%.2f", min_value=0.0, step=10.0),
            "Frequency": st.column_config.SelectboxColumn(options=FREQUENCIES, required=True),
            "Start Date": st.column_config.DateColumn(),
            "End Date": st.column_config.DateColumn(),
        },
        key="exp_editor",
    )
    st.session_state.expenses = edited

    st.download_button(
        "💾 Download expenses CSV",
        edited.to_csv(index=False).encode(),
        file_name="expenses.csv",
        mime="text/csv",
    )

    exp_daily = {}
    for cat, grp in edited.dropna(subset=["Category"]).groupby("Category"):
        exp_daily[cat] = expense_daily_series(grp, start, end)
    exp_df = pd.DataFrame(exp_daily, index=full_idx).fillna(0.0)
    if not exp_df.empty:
        st.subheader("Expenses in selected range")
        summary = exp_df.sum().rename("Total").reset_index().rename(columns={"index": "Category"})
        a, b = st.columns([1, 2])
        a.dataframe(summary.style.format({"Total": "${:,.2f}"}), hide_index=True, use_container_width=True)
        a.metric("Total expenses", f"${exp_df.values.sum():,.2f}")
        f = px.pie(summary[summary["Total"] > 0], names="Category", values="Total", hole=0.4)
        f.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
        b.plotly_chart(f, use_container_width=True)

# ----------------------------------------------------------------------------
# Profit & Loss
# ----------------------------------------------------------------------------
with tab_pl:
    if tx_f.empty:
        st.info("Upload transaction files to compute profit & loss.")
    else:
        total_exp = exp_df.sum(axis=1) if not exp_df.empty else pd.Series(0.0, index=full_idx)
        pl = pd.DataFrame(
            {
                "Net Sales": daily["Net Sales"],
                "Processing Fees": daily["Processing Fees"],
                "Operating Expenses": total_exp,
            }
        )
        pl["Profit"] = pl["Net Sales"] - pl["Processing Fees"] - pl["Operating Expenses"]

        rev, fees_t, exp_t, prof = (pl["Net Sales"].sum(), pl["Processing Fees"].sum(),
                                    pl["Operating Expenses"].sum(), pl["Profit"].sum())
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Net sales", f"${rev:,.0f}")
        c2.metric("Processing fees", f"${fees_t:,.0f}")
        c3.metric("Operating expenses", f"${exp_t:,.0f}")
        c4.metric("Estimated profit", f"${prof:,.0f}")
        c5.metric("Margin", f"{prof / rev * 100:.1f}%" if rev else "–")

        be_days = (pl["Net Sales"] - pl["Processing Fees"]).sum()
        if exp_t > 0 and be_days > 0:
            st.caption(f"Expenses consume **{exp_t / be_days * 100:.0f}%** of sales after fees.")

        st.subheader(f"Daily profit – {window}-day rolling average")
        f = go.Figure()
        f.add_scatter(x=pl.index, y=pl["Net Sales"].rolling(window, min_periods=1).mean(), name="Net sales")
        f.add_scatter(x=pl.index, y=pl["Operating Expenses"].rolling(window, min_periods=1).mean(), name="Expenses")
        f.add_scatter(x=pl.index, y=pl["Profit"].rolling(window, min_periods=1).mean(), name="Profit",
                      line=dict(width=3))
        f.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h"))
        st.plotly_chart(f, use_container_width=True)

        st.subheader("Monthly P&L")
        m = pl.resample("MS").sum()
        m.index = m.index.strftime("%Y-%m")
        m["Margin %"] = (m["Profit"] / m["Net Sales"].replace(0, pd.NA) * 100).astype(float)
        st.dataframe(
            m.style.format({c: "${:,.0f}" for c in m.columns if c != "Margin %"} | {"Margin %": "{:.1f}%"}),
            use_container_width=True,
        )
        st.download_button("💾 Download monthly P&L", m.to_csv().encode(), "monthly_pl.csv", "text/csv")

# ----------------------------------------------------------------------------
# Raw data
# ----------------------------------------------------------------------------
with tab_data:
    if not daily.empty:
        st.subheader("Daily summary")
        d = daily.copy()
        d["Rolling Net Sales"] = d["Net Sales"].rolling(window, min_periods=1).mean()
        st.dataframe(d, use_container_width=True)
        st.download_button("💾 Download daily summary", d.to_csv().encode(), "daily_summary.csv", "text/csv")
    st.caption(f"{len(tx_f):,} transaction rows and {len(items_f):,} item rows in the selected range.")
