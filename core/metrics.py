"""Approved metric functions.

The AI analyst can only answer by calling these named, read-only functions. Each one takes an explicit
date range so every answer can state exactly what it measured.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from core.data import DAYPARTS, WEEKDAYS

DIMENSIONS = ["day", "week", "month", "weekday", "daypart", "hour", "category", "item", "dining_option"]
METRICS = ["net_sales", "gross_sales", "transactions", "avg_ticket", "tips", "discounts", "refunds", "units"]


@dataclass
class MetricFn:
    name: str
    description: str
    fn: Callable
    params: dict  # json-schema properties


REGISTRY: dict[str, MetricFn] = {}

_DATE = {"type": "string", "description": "ISO date YYYY-MM-DD (inclusive)"}


def approved(description: str, **params):
    def wrap(fn):
        REGISTRY[fn.__name__] = MetricFn(fn.__name__, description, fn, params)
        return fn
    return wrap


class Metrics:
    """Bound to one dataset. Methods mirror REGISTRY entries."""

    def __init__(self, tx: pd.DataFrame, items: pd.DataFrame):
        self.tx = tx
        self.items = items
        self.is_pay = tx["Event Type"].eq("Payment") if not tx.empty and "Event Type" in tx else None

    # helpers -----------------------------------------------------------
    def _tx(self, start, end) -> pd.DataFrame:
        if self.tx.empty:
            return self.tx
        m = (self.tx["Day"] >= pd.Timestamp(start)) & (self.tx["Day"] <= pd.Timestamp(end))
        return self.tx[m]

    def _items(self, start, end) -> pd.DataFrame:
        if self.items.empty:
            return self.items
        m = (self.items["Day"] >= pd.Timestamp(start)) & (self.items["Day"] <= pd.Timestamp(end))
        return self.items[m]

    @staticmethod
    def _key(df: pd.DataFrame, by: str) -> pd.Series:
        if by == "day":
            return df["Day"]
        if by == "week":
            return df["Day"].dt.to_period("W-SUN").dt.start_time
        if by == "month":
            return df["Day"].dt.to_period("M").dt.start_time
        if by == "weekday":
            return pd.Categorical(df["Day"].dt.day_name(), categories=WEEKDAYS, ordered=True)
        if by == "daypart":
            return pd.Categorical(df["Daypart"], categories=DAYPARTS, ordered=True)
        if by == "hour":
            return df["Hour"]
        if by == "category":
            return df["Category"].str.strip().replace("", "(none)")
        if by == "item":
            return df["Item"]
        if by == "dining_option":
            return df["Dining Option"].replace("", "(not set)")
        raise ValueError(f"unknown dimension {by}")

    def _scalar(self, metric: str, start, end) -> float:
        if metric in ("units",):
            it = self._items(start, end)
            return float(it["Qty"].sum()) if not it.empty else 0.0
        t = self._tx(start, end)
        if t.empty:
            return 0.0
        pay = t["Event Type"].eq("Payment")
        if metric == "net_sales":
            return float(t["Net Sales"].sum())
        if metric == "gross_sales":
            return float(t.loc[pay, "Gross Sales"].sum())
        if metric == "transactions":
            return float(pay.sum())
        if metric == "avg_ticket":
            n = pay.sum()
            return float(t.loc[pay, "Net Sales"].sum() / n) if n else 0.0
        if metric == "tips":
            return float(t["Tip"].sum())
        if metric == "discounts":
            return float(-t["Discounts"].sum())
        if metric == "refunds":
            return float(-t.loc[~pay, "Net Sales"].sum())
        raise ValueError(f"unknown metric {metric}")

    # approved functions --------------------------------------------------
    @approved("Total of one metric over a date range. Net sales include refunds netted against payments.",
              metric={"type": "string", "enum": METRICS}, start=_DATE, end=_DATE)
    def metric_total(self, metric: str, start: str, end: str) -> dict:
        return {"metric": metric, "start": start, "end": end, "value": round(self._scalar(metric, start, end), 2)}

    @approved("One metric broken down by a dimension over a date range.",
              metric={"type": "string", "enum": METRICS}, start=_DATE, end=_DATE,
              by={"type": "string", "enum": DIMENSIONS})
    def metric_by(self, metric: str, start: str, end: str, by: str) -> pd.DataFrame:
        if metric == "units" or by in ("category", "item"):
            df = self._items(start, end)
            if df.empty:
                return pd.DataFrame(columns=[by, metric])
            col = {"units": "Qty", "net_sales": "Net Sales", "gross_sales": "Gross Sales",
                   "discounts": "Discounts"}.get(metric, "Net Sales")
            vals = df.groupby(self._key(df, by), observed=False)[col].sum()
            if metric == "discounts":
                vals = -vals
            if metric == "transactions":
                vals = df.groupby(self._key(df, by), observed=False)["Transaction ID"].nunique()
        else:
            df = self._tx(start, end)
            if df.empty:
                return pd.DataFrame(columns=[by, metric])
            pay = df["Event Type"].eq("Payment")
            k = self._key(df, by)
            g = lambda s: s.groupby(k, observed=False).sum()  # noqa: E731
            if metric == "net_sales":
                vals = g(df["Net Sales"])
            elif metric == "gross_sales":
                vals = g(df["Gross Sales"].where(pay, 0))
            elif metric == "transactions":
                vals = g(pay.astype(int))
            elif metric == "avg_ticket":
                vals = g(df["Net Sales"].where(pay, 0)) / g(pay.astype(int)).replace(0, np.nan)
            elif metric == "tips":
                vals = g(df["Tip"])
            elif metric == "discounts":
                vals = -g(df["Discounts"])
            elif metric == "refunds":
                vals = -g(df["Net Sales"].where(~pay, 0))
            else:
                raise ValueError(metric)
        out = vals.rename(metric).reset_index()
        out.columns = [by, metric]
        if by in ("item",):
            out = out.sort_values(metric, ascending=False)
        return out

    @approved("Compare one metric between period A and period B, optionally broken down by a dimension.",
              metric={"type": "string", "enum": METRICS}, a_start=_DATE, a_end=_DATE, b_start=_DATE, b_end=_DATE,
              by={"type": "string", "enum": DIMENSIONS + ["none"]})
    def compare_periods(self, metric, a_start, a_end, b_start, b_end, by="none") -> dict:
        a, b = self._scalar(metric, a_start, a_end), self._scalar(metric, b_start, b_end)
        res = {"metric": metric, "a": round(a, 2), "b": round(b, 2),
               "change_pct": round((a - b) / b * 100, 1) if b else None}
        if by and by != "none":
            ta = self.metric_by(metric, a_start, a_end, by).set_index(by)[metric]
            tb = self.metric_by(metric, b_start, b_end, by).set_index(by)[metric]
            t = pd.DataFrame({"A": ta, "B": tb}).fillna(0)
            t["Change"] = t["A"] - t["B"]
            t["Change %"] = (t["Change"] / t["B"].replace(0, np.nan) * 100).round(1)
            res["breakdown"] = t.reset_index().rename(columns={"index": by})
        return res

    @approved("Top N items over a date range ranked by net sales or units.",
              start=_DATE, end=_DATE, n={"type": "integer"},
              rank_by={"type": "string", "enum": ["net_sales", "units"]})
    def top_items(self, start, end, n=10, rank_by="net_sales") -> pd.DataFrame:
        it = self._items(start, end)
        if it.empty:
            return pd.DataFrame(columns=["Item", "Category", "Units", "Net Sales"])
        t = it.groupby("Item").agg(Category=("Category", "first"), Units=("Qty", "sum"),
                                   **{"Net Sales": ("Net Sales", "sum")})
        col = "Units" if rank_by == "units" else "Net Sales"
        return t.sort_values(col, ascending=False).head(int(n)).reset_index()

    @approved("Items whose net sales changed most between period A and period B.",
              a_start=_DATE, a_end=_DATE, b_start=_DATE, b_end=_DATE, n={"type": "integer"})
    def item_movers(self, a_start, a_end, b_start, b_end, n=5) -> pd.DataFrame:
        a = self.metric_by("net_sales", a_start, a_end, "item").set_index("item")["net_sales"]
        b = self.metric_by("net_sales", b_start, b_end, "item").set_index("item")["net_sales"]
        t = pd.DataFrame({"A": a, "B": b}).fillna(0)
        t["Change"] = t["A"] - t["B"]
        t = t.reindex(t["Change"].abs().sort_values(ascending=False).index).head(int(n))
        return t.reset_index(names="Item")

    @approved("Days whose net sales were unusually high or low against the trailing rolling baseline.",
              start=_DATE, end=_DATE, window={"type": "integer"}, threshold={"type": "number"})
    def anomalies(self, start, end, window=28, threshold=2.0) -> pd.DataFrame:
        if self.tx.empty:
            return pd.DataFrame()
        d = self.tx.groupby("Day")["Net Sales"].sum()
        d = d.reindex(pd.date_range(d.index.min(), d.index.max()), fill_value=0)
        dow = d.index.dayofweek
        # baseline: same weekday over trailing `window` days
        base = pd.Series(index=d.index, dtype=float)
        sd = pd.Series(index=d.index, dtype=float)
        for w in range(7):
            s = d[dow == w]
            k = max(2, window // 7)
            base[s.index] = s.shift(1).rolling(k, min_periods=2).median()
            sd[s.index] = s.shift(1).rolling(k, min_periods=2).std()
        z = (d - base) / sd.replace(0, np.nan)
        out = pd.DataFrame({"Net Sales": d, "Baseline": base, "z": z})
        out = out[(out.index >= pd.Timestamp(start)) & (out.index <= pd.Timestamp(end))]
        out = out[(out["z"].abs() >= threshold) & (out["Baseline"] > 50)]
        out["Change %"] = ((out["Net Sales"] - out["Baseline"]) / out["Baseline"] * 100).round(0)
        out["Weekday"] = out.index.day_name()
        return out.reset_index(names="Day").sort_values("Day", ascending=False)

    @approved("Refund count and amount grouped by refund reason over a date range.", start=_DATE, end=_DATE)
    def refunds_by_reason(self, start, end) -> pd.DataFrame:
        t = self._tx(start, end)
        r = t[t["Event Type"].eq("Refund")] if not t.empty else t
        if r.empty:
            return pd.DataFrame(columns=["Reason", "Count", "Amount"])
        g = r.assign(Reason=r["Refund Reason"].replace("", "(no reason)")).groupby("Reason")
        out = pd.DataFrame({"Count": g.size(), "Amount": -g["Net Sales"].sum()})
        return out.sort_values("Amount", ascending=False).reset_index()

    @approved("Best and worst trading days (by net sales) in a date range, excluding closed days.",
              start=_DATE, end=_DATE, n={"type": "integer"})
    def best_worst_days(self, start, end, n=3) -> dict:
        t = self._tx(start, end)
        d = t.groupby("Day")["Net Sales"].sum()
        d = d[d > 0]
        return {"best": d.nlargest(int(n)).round(2).to_dict(), "worst": d.nsmallest(int(n)).round(2).to_dict()}


def tool_specs() -> list[dict]:
    """Anthropic tool definitions for every approved function."""
    specs = []
    for f in REGISTRY.values():
        sig = inspect.signature(f.fn)
        required = [p for p, v in sig.parameters.items() if p != "self" and v.default is inspect._empty]
        specs.append({"name": f.name, "description": f.description,
                      "input_schema": {"type": "object", "properties": f.params, "required": required}})
    return specs


def call(m: Metrics, name: str, **kwargs):
    if name not in REGISTRY:
        raise ValueError(f"{name} is not an approved metric function")
    return getattr(m, name)(**kwargs)


def fmt_call(name: str, **kwargs) -> str:
    args = ", ".join(f"{k}={v!r}" if not isinstance(v, str) else f"{k}={v}" for k, v in kwargs.items())
    return f"{name}({args})"
