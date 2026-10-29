"""AI analyst: turns a plain-language question into calls to approved metric functions.

If ANTHROPIC_API_KEY is set (env or Streamlit secrets) and the `anthropic` package is installed, Claude picks
which approved functions to call via tool use. Otherwise a built-in rule-based planner does it. Either way the
answer only ever contains numbers returned by approved functions, and lists every call it made.
"""

from __future__ import annotations

import calendar
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from core.data import DAYPART_HOURS
from core.metrics import REGISTRY, Metrics, call, fmt_call, tool_specs

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS |= {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
MONTHS.pop("may", None)
MONTHS["may"] = 5

METRIC_WORDS = [
    ("refunds", ["refund", "returned", "return"]),
    ("tips", ["tip"]),
    ("avg_ticket", ["ticket", "average order", "avg order", "basket", "spend per"]),
    ("transactions", ["transaction", "orders", "customers", "traffic", "visits", "how many sales"]),
    ("units", ["units", "how many items", "quantity", "sold the most"]),
    ("discounts", ["discount"]),
    ("gross_sales", ["gross"]),
]
DIM_WORDS = [
    ("daypart", ["daypart", "time of day", "morning", "afternoon", "evening", "midday", "lunch rush"]),
    ("hour", ["hour", "hourly"]),
    ("weekday", ["weekday", "day of week", "day of the week", "which day"]),
    ("category", ["category", "categories"]),
    ("item", ["by item", "items", "product", "menu"]),
    ("month", ["by month", "monthly", "each month", "per month", "trend"]),
    ("week", ["by week", "weekly"]),
    ("dining_option", ["for here", "to go", "dine", "takeout", "dining"]),
]
METRIC_LABEL = {"net_sales": "net sales", "gross_sales": "gross sales", "transactions": "transactions",
                "avg_ticket": "average ticket", "tips": "tips", "discounts": "discounts", "refunds": "refunds",
                "units": "units sold"}
MONEY_METRICS = {"net_sales", "gross_sales", "avg_ticket", "tips", "discounts", "refunds"}


@dataclass
class Period:
    start: date
    end: date
    label: str


@dataclass
class Answer:
    text: str
    calls: list[str] = field(default_factory=list)
    tables: list[tuple[str, pd.DataFrame]] = field(default_factory=list)
    bars: list[tuple[str, float]] | None = None
    range_note: str = ""
    engine: str = "rule-based"


def fmt(metric: str, v: float) -> str:
    if v is None:
        return "–"
    sign = "-" if v < 0 else ""
    if metric in MONEY_METRICS:
        return f"{sign}${abs(v):,.2f}" if metric == "avg_ticket" else f"{sign}${abs(v):,.0f}"
    return f"{v:,.0f}"


def month_period(y: int, m: int) -> Period:
    last = calendar.monthrange(y, m)[1]
    return Period(date(y, m, 1), date(y, m, last), f"{calendar.month_name[m]} {y}")


def prev_period(p: Period) -> Period:
    if p.start.day == 1 and (p.end + timedelta(days=1)).day == 1:  # whole month(s)
        pe = p.start - timedelta(days=1)
        months = (p.end.year - p.start.year) * 12 + p.end.month - p.start.month + 1
        y, m = pe.year, pe.month - months + 1
        while m <= 0:
            m += 12
            y -= 1
        ps = date(y, m, 1)
        if months == 1:
            return month_period(ps.year, ps.month)
        return Period(ps, pe, f"{ps:%b %Y}–{pe:%b %Y}")
    span = (p.end - p.start).days + 1
    pe = p.start - timedelta(days=1)
    ps = pe - timedelta(days=span - 1)
    return Period(ps, pe, f"{ps:%b %-d}–{pe:%b %-d, %Y}")


def parse_periods(q: str, data_min: date, data_max: date) -> list[Period]:
    ql = q.lower()
    found: list[tuple[int, Period]] = []

    for m in re.finditer(r"\bq([1-4])\s*(?:of\s*)?(20\d\d)\b", ql):
        qn, y = int(m.group(1)), int(m.group(2))
        s = date(y, 3 * qn - 2, 1)
        e = date(y, 3 * qn, calendar.monthrange(y, 3 * qn)[1])
        found.append((m.start(), Period(s, e, f"Q{qn} {y}")))

    month_re = r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b\.?(?:\s+(?:of\s+)?(20\d\d))?"
    for m in re.finditer(month_re, ql):
        name = m.group(1)
        if name == "may" and not m.group(2) and re.search(r"\bmay\s+(i|we|you|be|have)\b", ql[m.start():m.start() + 8]):
            continue
        mi = MONTHS[name]
        if m.group(2):
            y = int(m.group(2))
        else:  # latest year in the data that contains that month
            y = data_max.year if mi <= data_max.month else data_max.year - 1
        found.append((m.start(), month_period(y, mi)))

    for m in re.finditer(r"\b(?:in|for|during|of)?\s*(20\d\d)\b", ql):
        y = int(m.group(1))
        if any(abs(pos - m.start()) < 12 for pos, _ in found):
            continue
        found.append((m.start(), Period(date(y, 1, 1), min(date(y, 12, 31), data_max), str(y))))

    rel = [
        (r"\blast month\b", lambda: prev_period(month_period(data_max.year, data_max.month))
            if data_max.day < 28 else month_period(data_max.year, data_max.month)),
        (r"\bthis month\b", lambda: month_period(data_max.year, data_max.month)),
        (r"\blast week\b", lambda: Period(data_max - timedelta(days=6), data_max, "the last 7 days")),
        (r"\blast (\d+) days\b", None),
        (r"\blast year\b", lambda: Period(date(data_max.year - 1, 1, 1), date(data_max.year - 1, 12, 31),
                                         str(data_max.year - 1))),
        (r"\bthis year\b|\bytd\b|year to date", lambda: Period(date(data_max.year, 1, 1), data_max,
                                                               f"{data_max.year} to date")),
    ]
    for pat, fn in rel:
        for m in re.finditer(pat, ql):
            if fn is None:
                n = int(m.group(1))
                found.append((m.start(), Period(data_max - timedelta(days=n - 1), data_max, f"the last {n} days")))
            else:
                found.append((m.start(), fn()))

    found.sort(key=lambda x: x[0])
    out = []
    for _, p in found:
        p = Period(max(p.start, data_min), min(p.end, data_max), p.label)
        if p.start <= p.end and all((p.start, p.end) != (o.start, o.end) for o in out):
            out.append(p)
    return out


def detect(words: list[tuple[str, list[str]]], q: str, default=None):
    ql = q.lower()
    for key, ws in words:
        if any(w in ql for w in ws):
            return key
    return default


# Rule-based planner -------------------------------------------------------------------
def answer_rule_based(q: str, m: Metrics, default: Period, data_min: date, data_max: date, window: int) -> Answer:
    ql = q.lower()
    periods = parse_periods(q, data_min, data_max)
    metric = detect(METRIC_WORDS, q, "net_sales")
    dim = detect(DIM_WORDS, q)
    calls: list[str] = []

    def run(name, **kw):
        calls.append(fmt_call(name, **kw))
        return call(m, name, **kw)

    iso = lambda d: d.isoformat()  # noqa: E731

    # Anomalies --------------------------------------------------------------------------
    if re.search(r"unusual|anomal|outlier|weird|strange|spike|odd day|flag", ql):
        p = periods[0] if periods else default
        df = run("anomalies", start=iso(p.start), end=iso(p.end), window=window * 4 if window < 14 else window,
                 threshold=2.0)
        if df.empty:
            text = f"No days in {p.label} moved more than 2 standard deviations from their same-weekday baseline."
        else:
            lows, highs = (df["Change %"] < 0).sum(), (df["Change %"] > 0).sum()
            worst = df.loc[df["Change %"].idxmin()] if lows else None
            text = f"I flagged **{len(df)} unusual day{'s' if len(df) != 1 else ''}** in {p.label}: {lows} low, {highs} high."
            if worst is not None:
                text += (f" The biggest drop was **{worst['Day']:%a %b %-d, %Y}** at ${worst['Net Sales']:,.0f}, "
                         f"{abs(worst['Change %']):.0f}% under its usual ${worst['Baseline']:,.0f} for a {worst['Weekday']}.")
        show = df.assign(Day=df["Day"].dt.strftime("%a %Y-%m-%d"))[["Day", "Net Sales", "Baseline", "Change %"]] \
            if not df.empty else df
        return Answer(text, calls, [("Unusual days", show)] if not df.empty else [],
                      range_note=f"{p.start} to {p.end}")

    # Refund reasons ---------------------------------------------------------------------
    if metric == "refunds" and re.search(r"why|reason", ql):
        p = periods[0] if periods else default
        df = run("refunds_by_reason", start=iso(p.start), end=iso(p.end))
        tot = run("metric_total", metric="refunds", start=iso(p.start), end=iso(p.end))["value"]
        if df.empty:
            return Answer(f"There were no refunds in {p.label}.", calls, range_note=f"{p.start} to {p.end}")
        top = df.iloc[0]
        text = (f"Refunds in {p.label} totalled **${tot:,.2f}** across {int(df['Count'].sum())} refunds. "
                f"The most common reason by value was **{top['Reason']}** (${top['Amount']:,.2f}, {int(top['Count'])} refunds).")
        return Answer(text, calls, [("Refunds by reason", df)], range_note=f"{p.start} to {p.end}")

    # Top items --------------------------------------------------------------------------
    if re.search(r"\b(top|best|most popular|best[- ]selling|sold the most|worst|least)\b", ql) and \
            (dim in (None, "item", "category") and re.search(r"item|product|sell|sold|seller|menu|drink|food", ql)):
        p = periods[0] if periods else default
        rank = "units" if re.search(r"units|quantity|how many|most popular|sold the most", ql) else "net_sales"
        n = int(re.search(r"\btop (\d+)", ql).group(1)) if re.search(r"\btop (\d+)", ql) else 10
        df = run("top_items", start=iso(p.start), end=iso(p.end), n=n, rank_by=rank)
        if df.empty:
            return Answer(f"No item data for {p.label}.", calls)
        t0 = df.iloc[0]
        text = (f"In {p.label}, the top item by {'units' if rank == 'units' else 'net sales'} was **{t0['Item']}** "
                f"({int(t0['Units']):,} units, ${t0['Net Sales']:,.0f}).")
        return Answer(text, calls, [(f"Top {n} items", df)], range_note=f"{p.start} to {p.end}")

    # Comparisons / why questions --------------------------------------------------------
    is_why = bool(re.search(r"\bwhy\b|slow|slower|down|drop|dip|decline|worse|bad|weak|up\b|grow|better|busier", ql))
    is_cmp = bool(re.search(r"\bvs\.?\b|versus|compare|compared|than|against", ql)) or len(periods) >= 2
    if (is_why or is_cmp) and periods:
        a = periods[0]
        b = periods[1] if len(periods) >= 2 else prev_period(a)
        # "Why was August slower than July": a=Aug, b=Jul
        by = dim or ("daypart" if metric != "units" else "category")
        res = run("compare_periods", metric=metric, a_start=iso(a.start), a_end=iso(a.end),
                  b_start=iso(b.start), b_end=iso(b.end), by=by)
        ch = res["change_pct"]
        direction = "up" if (ch or 0) >= 0 else "down"
        label = METRIC_LABEL[metric]
        text = (f"{a.label} {label} were **{fmt(metric, res['a'])}**, {direction} "
                f"**{abs(ch or 0):.1f}%** on {b.label} ({fmt(metric, res['b'])}).")
        asked_slow = bool(re.search(r"slow|down|drop|dip|decline|worse|weak|bad", ql))
        if asked_slow and (ch or 0) >= 0:
            text += " So the period was not slower overall."
        bars = None
        tables = []
        bd = res.get("breakdown")
        if bd is not None and not bd.empty:
            bd = bd[(bd["A"] != 0) | (bd["B"] != 0)]
            # ignore slivers (<2% of either period) so a $34 -> $0 evening doesn't headline the answer
            big = bd[(bd["A"].abs() >= 0.02 * bd["A"].abs().sum()) | (bd["B"].abs() >= 0.02 * bd["B"].abs().sum())]
            big = big if not big.empty else bd
            worst = big.loc[big["Change"].idxmin()]
            best = big.loc[big["Change"].idxmax()]
            name = str(worst[by])
            hours = f" ({DAYPART_HOURS[name]})" if by == "daypart" and name in DAYPART_HOURS else ""
            if worst["Change"] < 0:
                wp = f"down {abs(worst['Change %']):.1f}%, " if pd.notna(worst["Change %"]) else ""
                text += (f" By {by.replace('_', ' ')}, the part that fell most was **{name}{hours}**, "
                         f"{wp}{fmt(metric, worst['B'])} → {fmt(metric, worst['A'])}.")
            elif asked_slow:
                text += f" Every {by.replace('_', ' ')} was up."
            if best["Change"] > 0 and str(best[by]) != name:
                bp = f", up {best['Change %']:.1f}%" if pd.notna(best["Change %"]) else ""
                text += f" {best[by]} added the most ({fmt(metric, best['Change'])}{bp})."
            if by in ("daypart", "weekday") or len(big) <= 8:
                bars = [(str(r[by]), float(r["Change %"]) if pd.notna(r["Change %"]) else 0.0) for _, r in big.iterrows()]
            tables.append((f"{label.capitalize()} by {by.replace('_', ' ')}",
                           bd.rename(columns={"A": a.label, "B": b.label})))
        if metric in ("net_sales", "units") and is_why:
            mv = run("item_movers", a_start=iso(a.start), a_end=iso(a.end), b_start=iso(b.start),
                     b_end=iso(b.end), n=6)
            if not mv.empty:
                drop = mv[mv["Change"] < 0].head(2)
                if not drop.empty:
                    text += " Biggest item declines: " + ", ".join(
                        f"{r['Item']} ({fmt('net_sales', r['Change'])})" for _, r in drop.iterrows()) + "."
                tables.append(("Item movers", mv.rename(columns={"A": a.label, "B": b.label})))
        return Answer(text, calls, tables, bars, range_note=f"{a.label} ({a.start} to {a.end}) vs {b.label} ({b.start} to {b.end})")

    # Plain total, optionally broken down -------------------------------------------------
    p = periods[0] if periods else default
    tot = run("metric_total", metric=metric, start=iso(p.start), end=iso(p.end))["value"]
    text = f"{METRIC_LABEL[metric].capitalize()} for {p.label}: **{fmt(metric, tot)}**."
    tables = []
    if dim:
        df = run("metric_by", metric=metric, start=iso(p.start), end=iso(p.end), by=dim)
        df = df[df[metric].fillna(0) != 0]
        if dim == "item":
            df = df.head(15)
        if not df.empty:
            top = df.loc[df[metric].idxmax()]
            k = top[dim]
            k = k.strftime("%b %Y") if isinstance(k, pd.Timestamp) else k
            text += f" Highest {dim.replace('_', ' ')}: **{k}** ({fmt(metric, top[metric])})."
            if isinstance(df[dim].iloc[0], pd.Timestamp):
                df[dim] = df[dim].dt.strftime("%Y-%m-%d" if dim in ("day", "week") else "%b %Y")
            tables.append((f"{METRIC_LABEL[metric].capitalize()} by {dim.replace('_', ' ')}", df))
    return Answer(text, calls, tables, range_note=f"{p.start} to {p.end}")


# Claude-backed planner ----------------------------------------------------------------
def api_key() -> str | None:
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    try:
        import streamlit as st
        return st.secrets.get("ANTHROPIC_API_KEY")  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001
        return None


def claude_available() -> bool:
    if not api_key():
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _jsonable(x):
    if isinstance(x, pd.DataFrame):
        return json.loads(x.head(40).to_json(orient="records", date_format="iso"))
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (pd.Timestamp, date)):
        return x.isoformat()
    return x


def answer_claude(q: str, m: Metrics, default: Period, data_min: date, data_max: date, history: list[dict]) -> Answer:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key())
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    system = (
        "You are the analyst inside a cafe's sales dashboard. Answer the owner's question in plain, friendly language, "
        "2-4 sentences. You may ONLY use numbers returned by the provided tools; never estimate or invent figures. "
        f"Data covers {data_min} to {data_max}. If no dates are given, use the selected range {default.start} to "
        f"{default.end}. Month names without a year mean the most recent such month in the data. Mention the date "
        "range you used. Dayparts: Morning before 11am, Midday 11am-1pm, Afternoon 1pm-5pm, Evening 5pm on."
    )
    msgs = [{"role": h["role"], "content": h["content"]} for h in history[-6:]] + [{"role": "user", "content": q}]
    calls, tables = [], []
    for _ in range(6):
        resp = client.messages.create(model=model, max_tokens=900, system=system, tools=tool_specs(), messages=msgs)
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return Answer(text, calls, tables, engine=f"Claude ({model})")
        msgs.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            try:
                out = call(m, b.name, **b.input)
                calls.append(fmt_call(b.name, **b.input))
                if isinstance(out, pd.DataFrame) and not out.empty:
                    tables.append((b.name.replace("_", " ").capitalize(), out))
                content = json.dumps(_jsonable(out), default=str)
            except Exception as e:  # noqa: BLE001
                content = f"error: {e}"
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": content})
        msgs.append({"role": "user", "content": results})
    return Answer("I couldn't finish that within the allowed number of metric calls.", calls, tables,
                  engine=f"Claude ({model})")


def ask(q: str, m: Metrics, default: Period, data_min: date, data_max: date, window: int,
        history: list[dict] | None = None, use_claude: bool = True) -> Answer:
    if use_claude and claude_available():
        try:
            return answer_claude(q, m, default, data_min, data_max, history or [])
        except Exception as e:  # noqa: BLE001
            a = answer_rule_based(q, m, default, data_min, data_max, window)
            a.text += f"\n\n_(Claude was unavailable: {e}; answered with the built-in planner.)_"
            return a
    return answer_rule_based(q, m, default, data_min, data_max, window)


N_FUNCTIONS = len(REGISTRY)
