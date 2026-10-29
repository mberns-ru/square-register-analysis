"""Loading, cleaning and aggregation of Square transaction / item exports."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

MONEY_COLS = [
    "Gross Sales", "Discounts", "Service Charges", "Net Sales", "Gift Card Sales",
    "Tax", "Tip", "Partial Refunds", "Total Collected", "Fees", "Net Total", "Card", "Cash",
    "Square Gift Card", "Other Tender", "Cash App",
]
ITEM_MONEY_COLS = ["Gross Sales", "Discounts", "Net Sales", "Tax"]

DAYPARTS = ["Morning", "Midday", "Afternoon", "Evening"]
DAYPART_HOURS = {"Morning": "before 11am", "Midday": "11am–1pm", "Afternoon": "1pm–5pm", "Evening": "5pm on"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def daypart(hour: pd.Series) -> pd.Series:
    bins = [-1, 10, 12, 16, 24]
    return pd.cut(hour, bins=bins, labels=DAYPARTS).astype("object")


def parse_money(series: pd.Series) -> pd.Series:
    """Convert strings like '$1,234.50', '-$3.00', '($3.00)' to floats."""
    if series.dtype.kind in "fi":
        return series.astype(float)
    s = series.astype(str).str.strip()
    neg = (s.str.startswith("(") & s.str.endswith(")")) | s.str.startswith("-")
    s = s.str.replace(r"[^0-9.]", "", regex=True)
    out = pd.to_numeric(s, errors="coerce").fillna(0.0)
    return out.where(~neg, -out)


@dataclass
class LoadReport:
    files: int = 0
    rows_read: int = 0
    rows_kept: int = 0
    unreadable: list[str] = field(default_factory=list)
    bad_dates: int = 0
    duplicates: int = 0
    voided: int = 0
    extra: dict[str, int] = field(default_factory=dict)


TX_KEEP = set(MONEY_COLS) | {"Date", "Time", "Transaction ID", "Payment ID", "Event Type", "Location",
                              "Dining Option", "Customer ID", "Staff Name", "Refund Reason", "Transaction Status",
                              "Deposit ID", "Source", "Channel"}
ITEM_KEEP = set(ITEM_MONEY_COLS) | {"Date", "Time", "Category", "Item", "Qty", "Price Point Name", "Transaction ID",
                                   "Payment ID", "Event Type", "Location", "Dining Option", "Channel"}
PERIOD_RE = re.compile(r"(\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2})")

Source = tuple  # (display name, bytes | Path)


def _read(src) -> pd.DataFrame:
    buf = io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src
    return pd.read_csv(buf, dtype=str, keep_default_na=False,
                       usecols=lambda c: c in TX_KEEP or c in ITEM_KEEP)


def _load(sources: list[Source], kind: str) -> tuple[pd.DataFrame, LoadReport]:
    rep = LoadReport(files=len(sources))
    frames, seen = [], {}
    money = MONEY_COLS if kind == "transactions" else ITEM_MONEY_COLS
    for name, src in sources:
        m = PERIOD_RE.search(name)
        period = m.group(1) if m else name
        if period in seen:  # same month uploaded twice
            rep.extra["Duplicate files skipped"] = rep.extra.get("Duplicate files skipped", 0) + 1
            continue
        try:
            df = _read(src)
        except Exception:  # noqa: BLE001
            rep.unreadable.append(name)
            continue
        if "Date" not in df.columns:
            rep.unreadable.append(name)
            continue
        seen[period] = name
        frames.append(df)
    if not frames:
        return pd.DataFrame(), rep

    df = pd.concat(frames, ignore_index=True)
    del frames
    rep.rows_read = len(df)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    rep.bad_dates = int(df["Date"].isna().sum())
    df = df.dropna(subset=["Date"])
    for c in money:
        if c in df.columns:
            df[c] = parse_money(df[c])
    if "Qty" in df.columns:
        df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce").fillna(0)
    if "Time" in df.columns:
        df["Hour"] = pd.to_datetime(df["Time"], format="%H:%M:%S", errors="coerce").dt.hour
        df["Daypart"] = daypart(df["Hour"])
    df["Day"] = df["Date"].dt.normalize()

    before = len(df)
    if kind == "transactions" and "Payment ID" in df.columns and (df["Payment ID"] != "").any():
        df = df.drop_duplicates(subset=["Payment ID", "Event Type"] if "Event Type" in df.columns else ["Payment ID"])
    rep.duplicates = before - len(df)

    if "Transaction Status" in df.columns:
        voided = df["Transaction Status"].eq("Voided")
        rep.voided = int(voided.sum())
        df = df[~voided]

    if kind == "transactions":
        pay = df["Event Type"].eq("Payment") if "Event Type" in df.columns else pd.Series(True, index=df.index)
        if "Customer ID" in df.columns:
            rep.extra["Payments without a customer"] = int((pay & df["Customer ID"].eq("")).sum())
        if "Cash" in df.columns and "Deposit ID" in df.columns:
            rep.extra["Cash sales (no deposit, expected)"] = int((pay & (df["Cash"] > 0) & df["Deposit ID"].eq("")).sum())
        rep.extra["Refund rows"] = int((~pay).sum())
    elif "Category" in df.columns:
        rep.extra["Items with no category"] = int(df["Category"].eq("").sum())
    rep.rows_kept = len(df)
    return df.reset_index(drop=True), rep


@st.cache_resource(show_spinner="Reading exports…", max_entries=3)
def load_dataset(signature: tuple, _tx_sources: list[Source], _item_sources: list[Source]) -> dict:
    """Loaded once per distinct set of files (signature) and shared, not copied, across reruns."""
    tx, tx_rep = _load(_tx_sources, "transactions") if _tx_sources else (pd.DataFrame(), None)
    items, it_rep = _load(_item_sources, "items") if _item_sources else (pd.DataFrame(), None)
    return {"tx": tx, "items": items, "tx_report": tx_rep, "items_report": it_rep,
            "daily": daily_table(tx) if not tx.empty else pd.DataFrame()}


def local_sources(kind: str) -> list[Source]:
    folder = DATA_DIR / kind
    if not folder.is_dir():
        return []
    return [(p.name, p) for p in sorted(folder.glob("*.csv"))]


def signature(sources: list[Source]) -> tuple:
    out = []
    for name, src in sources:
        if isinstance(src, Path):
            st_ = src.stat()
            out.append((name, st_.st_size, st_.st_mtime))
        else:
            out.append((name, len(src), hashlib.md5(src[:65536] + src[-65536:]).hexdigest()))
    return tuple(out)


# Aggregates -------------------------------------------------------------------
def daily_table(tx: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar day across the whole dataset. Refunds are netted in."""
    if tx.empty:
        return pd.DataFrame()
    is_pay = tx["Event Type"].eq("Payment") if "Event Type" in tx.columns else pd.Series(True, index=tx.index)
    g = tx.groupby("Day")
    d = pd.DataFrame({
        "Gross Sales": g["Gross Sales"].sum(),
        "Net Sales": g["Net Sales"].sum(),
        "Tips": g["Tip"].sum(),
        "Tax": g["Tax"].sum(),
        "Discounts": g["Discounts"].sum(),
        "Processing Fees": -g["Fees"].sum(),
        "Total Collected": g["Total Collected"].sum(),
    })
    d["Transactions"] = is_pay.groupby(tx["Day"]).sum()
    d["Refunds"] = -tx.loc[~is_pay].groupby("Day")["Net Sales"].sum()
    idx = pd.date_range(d.index.min(), d.index.max(), freq="D")
    d = d.reindex(idx, fill_value=0).fillna(0)
    d["Avg Ticket"] = (d["Net Sales"] / d["Transactions"]).where(d["Transactions"] > 0)
    d.index.name = "Day"
    return d


@dataclass
class Ctx:
    tx_all: pd.DataFrame
    items_all: pd.DataFrame
    tx: pd.DataFrame
    items: pd.DataFrame
    daily_all: pd.DataFrame
    daily: pd.DataFrame
    start: date
    end: date
    window: int
    tx_report: LoadReport | None
    items_report: LoadReport | None

    @property
    def has_tx(self) -> bool:
        return not self.tx.empty

    @property
    def has_items(self) -> bool:
        return not self.items.empty

    def prior_range(self) -> tuple[date, date]:
        span = (pd.Timestamp(self.end) - pd.Timestamp(self.start)).days + 1
        pe = pd.Timestamp(self.start) - pd.Timedelta(days=1)
        ps = pe - pd.Timedelta(days=span - 1)
        return ps.date(), pe.date()

    def range_label(self) -> str:
        return f"{self.start:%b %-d, %Y} – {self.end:%b %-d, %Y}"


def filter_range(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    col = df["Day"] if "Day" in df.columns else df.index
    m = (col >= pd.Timestamp(start)) & (col <= pd.Timestamp(end))
    return df[m]
