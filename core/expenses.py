"""Expense book: storage, allocation to days, and drafting from plain-language descriptions."""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import streamlit as st

EXPENSE_CATEGORIES = ["Rent", "Payroll", "Utilities / Bills", "Supplies", "Ingredients", "Insurance",
                      "Marketing", "Equipment", "Loan / Debt", "Taxes", "Other"]
FREQUENCIES = ["Monthly", "Weekly", "Yearly", "One-time"]
STATUSES = ["Estimated", "Confirmed", "Document-backed"]
COLUMNS = ["Category", "Description", "Vendor", "Amount", "Frequency", "Start Date", "End Date", "Status"]


def empty_book() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMNS}).astype({"Amount": float})


def sample_book(start: date) -> pd.DataFrame:
    """Placeholder figures for a small cafe so the profit views have something to show.
    Every row is marked Estimated; replace them with real numbers."""
    rows = [
        ("Rent", "Storefront lease", "Landlord", 3000.0, "Monthly"),
        ("Payroll", "Staff wages", "", 1700.0, "Weekly"),
        ("Utilities / Bills", "Electric, gas, water, internet", "", 650.0, "Monthly"),
        ("Ingredients", "Coffee, dairy, bakery, produce", "", 1400.0, "Weekly"),
        ("Supplies", "Cups, lids, napkins, cleaning", "", 300.0, "Monthly"),
        ("Insurance", "General liability", "", 2400.0, "Yearly"),
    ]
    df = pd.DataFrame(rows, columns=["Category", "Description", "Vendor", "Amount", "Frequency"])
    df["Start Date"] = start
    df["End Date"] = None
    df["Status"] = "Estimated"
    return df[COLUMNS]


def book() -> pd.DataFrame:
    if "expenses" not in st.session_state:
        st.session_state.expenses = empty_book()
    df = st.session_state.expenses
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = "Estimated" if c == "Status" else None
    return df[COLUMNS]


def daily_allocation(expenses: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Spread each expense across days in [start, end], one column per category."""
    idx = pd.date_range(start, end, freq="D")
    out: dict[str, pd.Series] = {}
    if expenses is None or expenses.empty:
        return pd.DataFrame(index=idx)
    for _, r in expenses.iterrows():
        amt, freq, cat = r.get("Amount"), r.get("Frequency"), r.get("Category") or "Other"
        if pd.isna(amt) or not amt or freq not in FREQUENCIES:
            continue
        s = pd.to_datetime(r.get("Start Date"), errors="coerce")
        e = pd.to_datetime(r.get("End Date"), errors="coerce")
        col = out.setdefault(cat, pd.Series(0.0, index=idx))
        if freq == "One-time":
            if pd.notna(s) and s.normalize() in col.index:
                col.loc[s.normalize()] += float(amt)
            continue
        per_day = {"Monthly": amt * 12 / 365, "Weekly": amt / 7, "Yearly": amt / 365}[freq]
        mask = pd.Series(True, index=idx)
        if pd.notna(s):
            mask &= idx >= s
        if pd.notna(e):
            mask &= idx <= e
        col[mask] += float(per_day)
    return pd.DataFrame(out, index=idx).fillna(0.0)


# Drafting ---------------------------------------------------------------------
NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
             "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a dozen": 12, "dozen": 12}
CATEGORY_HINTS = {
    "Ingredients": ["milk", "flour", "sugar", "egg", "butter", "coffee", "bean", "espresso", "cream", "cheese",
                    "bread", "bagel", "syrup", "tea", "fruit", "produce", "oat", "almond", "chocolate", "meat"],
    "Supplies": ["cup", "lid", "napkin", "straw", "sleeve", "bag", "glove", "towel", "soap", "clean", "box",
                 "container", "foil", "wrap"],
    "Equipment": ["grinder", "machine", "blender", "fridge", "oven", "repair", "kettle"],
    "Utilities / Bills": ["electric", "gas bill", "water bill", "internet", "phone"],
    "Marketing": ["flyer", "ad ", "ads", "instagram", "sign", "print"],
}
VENDOR_RE = re.compile(r"\b(?i:went to|shopped at|at|from|bought from)\s+([A-Z][\w&'.]*(?:\s+[A-Z][\w&'.]*)*)")
TOTAL_RE = re.compile(r"(?:spent|paid|total(?:ed)?|came to|cost)\s+(?:about|around|roughly|~)?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)", re.I)
PRICE_RE = re.compile(r"(?:for|at|@)\s*\$\s*([\d,]+(?:\.\d{1,2})?)(?:\s*(?:each|ea))?", re.I)
QTY_RE = re.compile(r"^\s*(\d+(?:\.\d+)?|a dozen|dozen|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b\s*(.*)$", re.I)


def guess_category(text: str) -> str:
    t = f" {text.lower()} "
    for cat, words in CATEGORY_HINTS.items():
        if any(w in t for w in words):
            return cat
    return "Other"


def last_unit_price(item: str, history: pd.DataFrame) -> float | None:
    """Look up the most recent unit price for a similar line in confirmed history."""
    if history is None or history.empty:
        return None
    key = " ".join(w for w in re.findall(r"[a-z]+", item.lower()) if len(w) > 2)
    if not key:
        return None
    for _, r in history.iloc[::-1].iterrows():
        d = str(r.get("Description", "")).lower()
        words = key.split()
        if words and sum(w in d for w in words) >= max(1, len(words) // 2 + (len(words) > 1)):
            m = re.search(r"@\s*\$([\d.]+)", d)
            if m:
                return float(m.group(1))
    return None


def draft_from_text(text: str, history: pd.DataFrame | None = None) -> dict:
    """Rule-based extraction: vendor, stated total and line items. Returns a draft dict."""
    vendor = ""
    m = VENDOR_RE.search(text)
    if m:
        vendor = m.group(1).strip().rstrip(".")
    total = None
    m = TOTAL_RE.search(text)
    if m:
        total = float(m.group(1).replace(",", ""))

    body = TOTAL_RE.sub("", text)
    body = VENDOR_RE.sub("", body)
    body = re.sub(r"^\s*(?:i\s+)?(?:bought|got|picked up|purchased)\s+", "", body, flags=re.I)
    parts = re.split(r"\.(?=\s|$)|[;\n]|,\s*|\s+and\s+|\s+plus\s+", body)
    lines = []
    for p in parts:
        p = re.sub(r"^\s*(?:and|plus|also)\s+", "", p.strip(), flags=re.I)
        p = re.sub(r"^\s*(?:i\s+)?(?:bought|got|picked up|purchased)\s+", "", p, flags=re.I)
        if len(p) < 3:
            continue
        price = None
        pm = PRICE_RE.search(p)
        if pm:
            price = float(pm.group(1).replace(",", ""))
            p = PRICE_RE.sub("", p).strip()
        qm = QTY_RE.match(p)
        if not qm:
            continue
        q_raw, rest = qm.group(1).lower(), qm.group(2)
        qty = float(NUM_WORDS.get(q_raw, q_raw)) if not q_raw.replace(".", "").isdigit() else float(q_raw)
        rest = re.sub(r"^(?:x\s+|of\s+)", "", rest.strip(), flags=re.I)
        if not rest or rest.lower().startswith(("dollar", "$", "about", "around")):
            continue
        name = re.sub(r"\b(?:bags?|gallons?|cases?|boxes?|packs?|sleeves?)\s+of\s+", lambda x: x.group(0), rest)
        name = name[0].upper() + name[1:]
        unit = price if price is not None else last_unit_price(name, history)
        lines.append({
            "Item": name, "Qty": qty, "Unit price": unit,
            "Category": guess_category(name),
            "Source": "stated" if price is not None else ("last invoice" if unit is not None else "needs price"),
        })
    return {"vendor": vendor, "stated_total": total, "lines": lines, "text": text}


def draft_summary(lines: pd.DataFrame, stated_total: float | None) -> tuple[float, float | None, list[str]]:
    lines = lines.copy()
    lines["Line total"] = lines["Qty"].astype(float) * pd.to_numeric(lines["Unit price"], errors="coerce")
    priced = lines["Line total"].fillna(0).sum()
    gap = None if stated_total is None else round(stated_total - priced, 2)
    issues = []
    missing = lines[lines["Unit price"].isna()]["Item"].tolist()
    if missing:
        issues.append("Needs a price: " + ", ".join(map(str, missing)))
    if gap is not None and abs(gap) >= 0.01:
        issues.append(f"Lines don't add up to the stated total (unaccounted ${gap:,.2f})")
    return priced, gap, issues
