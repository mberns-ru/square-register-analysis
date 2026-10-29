"""
Databased — Square Register sales analytics dashboard (Streamlit)

Upload monthly Square exports (transactions + items), or drop them into data/transactions and data/items,
then explore sales, items, expenses, refunds, forecasts and seasonality, or ask the AI analyst.

Run:
    pip install -r requirements.txt
    streamlit run app.py

Optional: set ANTHROPIC_API_KEY (env var or .streamlit/secrets.toml) to let Claude plan the AI analyst's
metric calls and read receipts. Without it, a built-in rule-based planner is used.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Databased · Sales Dashboard", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")

from core import theme as T  # noqa: E402
from core.data import Ctx, filter_range, load_dataset, local_sources, signature  # noqa: E402
from core import auth  # noqa: E402
from views import analyst, expenses, forecast, items, login, overview, refunds, reports, seasonality, settings  # noqa: E402

settings.apply_query_params()  # ?theme=ocean etc. in the URL
T.inject()

# ----------------------------------------------------------------------------
# Accounts (Supabase). Without SUPABASE_URL / SUPABASE_ANON_KEY the app runs in local mode.
# ----------------------------------------------------------------------------
if auth.enabled():
    auth.finish_oauth_if_returning()  # back from Google with ?code=...
    if auth.current() is None:
        login.render()
        st.stop()
    if not auth.current().businesses:
        login.render_first_business()
        st.stop()

# ----------------------------------------------------------------------------
# Data sources: uploads win; otherwise read the local data/ folder if present
# ----------------------------------------------------------------------------
logo, icon = T.logo_files()
st.logo(logo, size="large", icon_image=icon)

pages = {
    "Overview": st.Page(lambda: overview.render(st.session_state._ctx), title="Overview", icon=":material/home:",
                        url_path="overview", default=True),
    "Items": st.Page(lambda: items.render(st.session_state._ctx), title="Items", icon=":material/coffee:",
                     url_path="items"),
    "Expenses": st.Page(lambda: expenses.render(st.session_state._ctx), title="Expenses",
                        icon=":material/receipt_long:", url_path="expenses"),
    "Refunds": st.Page(lambda: refunds.render(st.session_state._ctx), title="Refunds", icon=":material/undo:",
                       url_path="refunds"),
    "Forecast": st.Page(lambda: forecast.render(st.session_state._ctx), title="Forecast",
                        icon=":material/trending_up:", url_path="forecast"),
    "Seasonality": st.Page(lambda: seasonality.render(st.session_state._ctx), title="Seasonality",
                           icon=":material/calendar_month:", url_path="seasonality"),
    "Reports": st.Page(lambda: reports.render(st.session_state._ctx), title="Reports",
                       icon=":material/description:", url_path="reports"),
    "Settings": st.Page(settings.render, title="Settings", icon=":material/settings:", url_path="settings"),
}
st.session_state._pages = pages
nav = st.navigation(list(pages.values()), position="sidebar")
login.sidebar_account()
if not auth.enabled():
    st.sidebar.caption("Local mode: accounts are off. Add Supabase keys to turn on sign-in.")

with st.sidebar:
    with st.expander("Data", icon=":material/upload:"):
        tx_files = st.file_uploader("Transaction CSVs", type="csv", accept_multiple_files=True, key="tx")
        item_files = st.file_uploader("Item CSVs", type="csv", accept_multiple_files=True, key="items_up")
        st.caption("Select every file in the folder at once (Ctrl/Cmd+A). Re-uploading a month is safe: "
                   "duplicates are dropped.")

tx_src = [(f.name, f.getvalue()) for f in tx_files] if tx_files else local_sources("transactions")
it_src = [(f.name, f.getvalue()) for f in item_files] if item_files else local_sources("items")
ds = load_dataset((signature(tx_src), signature(it_src)), tx_src, it_src)
tx_all, items_all, tx_rep, it_rep, daily_all = ds["tx"], ds["items"], ds["tx_report"], ds["items_report"], ds["daily"]

if nav.title == "Settings":  # works with or without data loaded
    nav.run()
    st.stop()

if tx_all.empty and items_all.empty:
    T.page_header("Welcome to Databased", "")
    with st.container(key="card_welcome"):
        T.card_header("Upload your Square exports to get started",
                      "Open the Data panel in the sidebar and select every CSV in your transactions and items folders.")
        st.markdown("Everything else — sales, rolling averages, refunds, forecasts and the AI analyst — "
                    "updates automatically from those files.")
    st.stop()

base = tx_all if not tx_all.empty else items_all
min_d, max_d = base["Day"].min().date(), base["Day"].max().date()

with st.sidebar:
    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    presets = {"Last 30 days": 30, "Last 90 days": 90, "Last 12 months": 365, "All time": None, "Custom": -1}
    choice = st.selectbox("Period", list(presets), index=1, key="preset")
    if presets[choice] == -1:
        rng = st.date_input("Date range", value=(max(min_d, max_d - pd.Timedelta(days=89)), max_d),
                            min_value=min_d, max_value=max_d)
        start, end = (rng if isinstance(rng, tuple) and len(rng) == 2 else (min_d, max_d))
    elif presets[choice] is None:
        start, end = min_d, max_d
    else:
        start, end = max(min_d, max_d - pd.Timedelta(days=presets[choice] - 1)), max_d
    window = st.select_slider("Rolling average (days)", options=[3, 7, 14, 28, 30, 60, 90], value=7)
    st.caption(f"Data: {min_d:%b %-d, %Y} – {max_d:%b %-d, %Y}")

st.session_state._ctx = Ctx(
    tx_all=tx_all, items_all=items_all,
    tx=filter_range(tx_all, start, end), items=filter_range(items_all, start, end),
    daily_all=daily_all,
    daily=filter_range(daily_all, start, end).reindex(pd.date_range(start, end), fill_value=0)
    if not daily_all.empty else daily_all,
    start=start, end=end, window=window, tx_report=tx_rep, items_report=it_rep,
)

analyst.render_panel(st.session_state._ctx)  # full-width, collapsible, on every data page
nav.run()
