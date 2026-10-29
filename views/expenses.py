from __future__ import annotations

import base64
import json
import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import theme as T
from core.analyst import api_key, claude_available
from core.data import Ctx
from core.expenses import (EXPENSE_CATEGORIES, FREQUENCIES, STATUSES, book, daily_allocation, draft_from_text,
                           draft_summary, empty_book, sample_book)

LINE_COLS = ["Item", "Qty", "Unit price", "Category", "Source"]


def _claude_extract(text: str | None, file) -> dict | None:
    """Ask Claude to read a purchase description or receipt into structured lines."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key())
    content = []
    if file is not None:
        data = base64.standard_b64encode(file.getvalue()).decode()
        if file.type == "application/pdf":
            content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}})
        else:
            content.append({"type": "image", "source": {"type": "base64", "media_type": file.type, "data": data}})
    content.append({"type": "text", "text": (
        "Extract this cafe purchase as JSON only, no prose: {\"vendor\": str, \"date\": \"YYYY-MM-DD\" or null, "
        "\"stated_total\": number or null, \"lines\": [{\"Item\": str, \"Qty\": number, \"Unit price\": number or null, "
        f"\"Category\": one of {EXPENSE_CATEGORIES}}}]}}. Use null for anything not stated; never guess prices.\n\n"
        + (text or ""))})
    resp = client.messages.create(model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"), max_tokens=1200,
                                  messages=[{"role": "user", "content": content}])
    raw = "".join(b.text for b in resp.content if b.type == "text")
    raw = raw[raw.find("{"): raw.rfind("}") + 1]
    out = json.loads(raw)
    for ln in out.get("lines", []):
        ln["Source"] = "receipt" if file is not None else ("stated" if ln.get("Unit price") is not None else "needs price")
    return out


def _start_draft(d: dict, doc_name: str | None = None) -> None:
    lines = pd.DataFrame(d.get("lines") or [], columns=LINE_COLS)
    if lines.empty:
        lines = pd.DataFrame([{"Item": "", "Qty": 1.0, "Unit price": None, "Category": "Other", "Source": "manual"}])
    lines["Qty"] = pd.to_numeric(lines["Qty"], errors="coerce").fillna(1.0)
    lines["Unit price"] = pd.to_numeric(lines["Unit price"], errors="coerce")
    st.session_state.draft = {
        "vendor": d.get("vendor") or "", "date": pd.to_datetime(d.get("date"), errors="coerce"),
        "stated_total": d.get("stated_total"), "lines": lines, "doc": doc_name, "text": d.get("text", ""),
    }


def _capture_panel(ctx: Ctx) -> None:
    T.card_header("Add expense", "Describe the purchase in plain language, or attach a receipt")
    if "exp_chat" not in st.session_state:
        st.session_state.exp_chat = []
    for role, msg in st.session_state.exp_chat[-4:]:
        cls = "bubble-q" if role == "user" else "bubble-a"
        align = "right" if role == "user" else "left"
        st.markdown(f'<div style="text-align:{align};margin:6px 0"><div class="{cls}" style="text-align:left">'
                    f'{T.esc(msg)}</div></div>', unsafe_allow_html=True)

    with st.form("exp_capture", clear_on_submit=True, border=False):
        text = st.text_area("Describe it", height=90, label_visibility="collapsed",
                            placeholder="e.g. Went to the wholesale club. 6 gallons of whole milk, two 25 lb bags of "
                                        "flour, and a sleeve of 12 oz cups. Spent about $140.")
        receipt = st.file_uploader("Receipt", type=["png", "jpg", "jpeg", "webp", "pdf"],
                                   label_visibility="collapsed")
        go_ = st.form_submit_button("Draft it", width="stretch")
    if go_ and (text.strip() or receipt is not None):
        st.session_state.exp_chat.append(("user", text.strip() or f"(receipt: {receipt.name})"))
        d = None
        if claude_available():
            try:
                d = _claude_extract(text, receipt)
                d["text"] = text
            except Exception as e:  # noqa: BLE001
                st.session_state.exp_chat.append(("assistant", f"Claude couldn't read that ({e}); using the built-in parser."))
        if d is None:
            d = draft_from_text(text, book()) if text.strip() else {"lines": [], "vendor": "", "stated_total": None}
        _start_draft(d, receipt.name if receipt is not None else None)
        lines = st.session_state.draft["lines"]
        need = lines["Unit price"].isna().sum()
        hist = (lines["Source"] == "last invoice").sum()
        msg = f"I drafted {len(lines)} line item{'s' if len(lines) != 1 else ''}."
        if hist:
            msg += f" {hist} price{'s' if hist > 1 else ''} came from your last invoice."
        if need:
            msg += f" {need} still need{'s' if need == 1 else ''} a price — fill {'it' if need == 1 else 'them'} in on the draft."
        if receipt is not None and not claude_available():
            msg += " I attached the receipt; add an API key to have it read automatically."
        st.session_state.exp_chat.append(("assistant", msg))
        st.rerun()
    st.caption("Nothing reaches the books until you confirm the draft.")


def _draft_panel() -> None:
    d = st.session_state.get("draft")
    T.card_header("Draft purchase", "Edit anything, then confirm")
    if not d:
        st.markdown(f'<p class="card-sub" style="padding:40px 0;text-align:center">No draft yet. Describe a purchase '
                    f'or drop a receipt on the left.</p>', unsafe_allow_html=True)
        return
    c1, c2 = st.columns(2)
    d["vendor"] = c1.text_input("Vendor", d["vendor"], key="dr_vendor")
    dt = d["date"] if pd.notna(d["date"]) else pd.Timestamp(date.today())
    d["date"] = pd.Timestamp(c2.date_input("Date", dt.date(), key="dr_date"))
    lines = st.data_editor(d["lines"], num_rows="dynamic", hide_index=True, width="stretch",
                           key="dr_lines", column_config={
                               "Qty": st.column_config.NumberColumn(min_value=0.0, step=1.0, format="%g"),
                               "Unit price": st.column_config.NumberColumn(format="$%.2f", min_value=0.0),
                               "Category": st.column_config.SelectboxColumn(options=EXPENSE_CATEGORIES),
                               "Source": st.column_config.TextColumn(disabled=True)})
    d["lines"] = lines
    stated = st.number_input("Receipt total stated", value=float(d["stated_total"] or 0.0), min_value=0.0,
                             step=1.0, format="%.2f", key="dr_total")
    d["stated_total"] = stated or None
    priced, gap, issues = draft_summary(lines, d["stated_total"])
    lt = lines["Qty"].astype(float) * pd.to_numeric(lines["Unit price"], errors="coerce")
    st.markdown(
        f'<div class="legend" style="font-size:.82rem;margin:4px 0 8px 0">'
        f'<span>Lines priced: <b>{T.money(priced, 2)}</b></span>'
        + (f'<span>Stated: <b>{T.money(d["stated_total"], 2)}</b></span>' if d["stated_total"] else "")
        + (f'<span style="color:{T.BAD}">Unaccounted: <b>{T.money(gap, 2)}</b></span>' if gap else "")
        + "</div>", unsafe_allow_html=True)
    status = "Document-backed" if d.get("doc") else "Confirmed"
    if issues:
        st.warning("Not ready to post. " + " · ".join(issues))
    b1, b2, b3 = st.columns(3)
    post_anyway = b2.button("Post anyway", type="secondary", width="stretch", disabled=not issues,
                            help="Posts as Estimated, using the stated total for any gap")
    if b1.button("Confirm and post", width="stretch", disabled=bool(issues)) or post_anyway:
        rows = []
        for (_, r), tot in zip(lines.iterrows(), lt):
            if not str(r["Item"]).strip() or pd.isna(tot):
                continue
            rows.append({"Category": r["Category"] or "Other",
                         "Description": f"{r['Item']} ×{r['Qty']:g} @ ${r['Unit price']:.2f}",
                         "Vendor": d["vendor"], "Amount": round(float(tot), 2), "Frequency": "One-time",
                         "Start Date": d["date"].date(), "End Date": None,
                         "Status": "Estimated" if post_anyway else status})
        if post_anyway and gap:
            rows.append({"Category": "Other", "Description": "Unitemized remainder of receipt", "Vendor": d["vendor"],
                         "Amount": round(float(gap), 2), "Frequency": "One-time", "Start Date": d["date"].date(),
                         "End Date": None, "Status": "Estimated"})
        if rows:
            st.session_state.expenses = pd.concat([book(), pd.DataFrame(rows)], ignore_index=True)
            st.session_state.exp_chat.append(("assistant", f"Posted {len(rows)} line(s) to the books, "
                                                           f"{T.money(sum(r['Amount'] for r in rows), 2)} total."))
        st.session_state.draft = None
        st.rerun()
    if b3.button("Discard", type="secondary", width="stretch"):
        st.session_state.draft = None
        st.rerun()


def render(ctx: Ctx) -> None:
    T.page_header("Expenses", ctx.range_label())
    left, right = st.columns([1, 1.25], gap="medium")
    with left, st.container(key="card_capture"):
        _capture_panel(ctx)
    with right, st.container(key="card_draft"):
        _draft_panel()

    exp = book()
    alloc = daily_allocation(exp, ctx.start, ctx.end)
    total = float(alloc.values.sum()) if not alloc.empty else 0.0
    counts = exp["Status"].value_counts() if not exp.empty else pd.Series(dtype=int)
    net = ctx.daily["Net Sales"].sum() if ctx.has_tx else 0
    T.tiles([
        T.tile("Expenses in period", T.money(total)),
        T.tile("Share of net sales", f"{total / net * 100:.0f}%" if net else "–"),
        T.tile("Estimated", f"{counts.get('Estimated', 0)}", "rows to firm up" if counts.get("Estimated", 0) else None, False),
        T.tile("Confirmed", f"{counts.get('Confirmed', 0)}"),
        T.tile("Document-backed", f"{counts.get('Document-backed', 0)}"),
    ])
    st.markdown("")

    a, b = st.columns([1.6, 1], gap="medium")
    with a, st.container(key="card_book"):
        c1, c2 = st.columns([3, 2], vertical_alignment="center")
        with c1:
            T.card_header("Expense book", "Recurring costs spread evenly by day; one-time costs land on their date")
        with c2:
            s1, s2 = st.columns(2)
            if s1.button("Sample data", type="secondary", width="stretch",
                         help="Load placeholder cafe expenses, all marked Estimated"):
                st.session_state.expenses = pd.concat([book(), sample_book(ctx.tx_all["Day"].min().date()
                                                                           if ctx.has_tx else ctx.start)],
                                                      ignore_index=True)
                st.rerun()
            if s2.button("Clear", type="secondary", width="stretch"):
                st.session_state.expenses = empty_book()
                st.rerun()
        edited = st.data_editor(exp, num_rows="dynamic", width="stretch", hide_index=True, key="exp_editor",
                                column_config={
                                    "Category": st.column_config.SelectboxColumn(options=EXPENSE_CATEGORIES, required=True),
                                    "Amount": st.column_config.NumberColumn(format="$%.2f", min_value=0.0, step=10.0),
                                    "Frequency": st.column_config.SelectboxColumn(options=FREQUENCIES, required=True),
                                    "Start Date": st.column_config.DateColumn(),
                                    "End Date": st.column_config.DateColumn(),
                                    "Status": st.column_config.SelectboxColumn(options=STATUSES, required=True),
                                })
        if not edited.equals(exp):
            st.session_state.expenses = edited
        d1, d2 = st.columns([1, 1])
        d1.download_button("Download expenses CSV", edited.to_csv(index=False).encode(), "expenses.csv", "text/csv",
                           width="stretch")
        up = d2.file_uploader("Load expenses CSV", type="csv", key="exp_up", label_visibility="collapsed")
        if up is not None and st.session_state.get("_exp_loaded") != up.name:
            try:
                loaded = pd.read_csv(up)
                for c in ("Start Date", "End Date"):
                    loaded[c] = pd.to_datetime(loaded[c], errors="coerce").dt.date
                for c in ("Vendor", "Status"):
                    if c not in loaded:
                        loaded[c] = "Estimated" if c == "Status" else ""
                st.session_state.expenses = loaded[list(exp.columns)]
                st.session_state._exp_loaded = up.name
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not load expenses: {e}")

    with b, st.container(key="card_expmix"):
        T.card_header("Where the money goes", "Allocated to the selected period")
        if total > 0:
            s = alloc.sum().sort_values(ascending=False)
            s = s[s > 0]
            fig = go.Figure(go.Pie(labels=s.index, values=s.values, hole=0.6, sort=False,
                                   marker=dict(colors=T.SERIES, line=dict(color="#fff", width=3)), textinfo="none",
                                   hovertemplate="%{label}: %{value:$,.0f} (%{percent})<extra></extra>"))
            fig.add_annotation(text=f"<b>{T.money(total)}</b>", showarrow=False, font=dict(size=18))
            fig.update_layout(legend=dict(orientation="v", x=1.02, y=0.5, yanchor="middle", xanchor="left"),
                              margin=dict(l=0, r=0, t=4, b=4))
            T.chart(fig, 260, key="exp_pie")
            m = alloc.sum(axis=1).resample("MS").sum()
            st.markdown(T.progress_bars([(f"{i:%b %Y}", v / m.max(), T.money(v)) for i, v in m.tail(4).items()],
                                        colors=[T.INDIGO, T.LAVENDER]), unsafe_allow_html=True)
        else:
            st.markdown('<p class="card-sub" style="padding:30px 0;text-align:center">No expenses yet. Add one above, '
                        'type into the book, or load sample data.</p>', unsafe_allow_html=True)
