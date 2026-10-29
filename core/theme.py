"""Visual theme: soft lavender canvas, white rounded cards, indigo + orange accents."""

from __future__ import annotations

import html

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Palette ---------------------------------------------------------------------
INDIGO = "#5B5BD6"
INDIGO_DARK = "#4A4AC0"
LAVENDER = "#A9AAF1"
LAVENDER_SOFT = "#DCDDFB"
ORANGE = "#EE8A4E"
PEACH = "#F6C09C"
CANVAS = "#E6EAFB"
CARD = "#FFFFFF"
INK = "#2D2E4A"
MUTED = "#8B8DA8"
GRID = "#EEF0FA"
GOOD = "#3BA776"
BAD = "#E0644A"

SERIES = [INDIGO, ORANGE, LAVENDER, PEACH, "#7FC8C2", "#C9A4E6", "#9AA0B8"]

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select {{
  font-family: 'Poppins', system-ui, sans-serif !important;
}}
.stApp {{ background: {CANVAS}; color: {INK}; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1500px; }}
h1, h2, h3, h4 {{ color: {INK}; font-weight: 600; letter-spacing: -0.01em; }}

/* Sidebar: solid indigo rail */
section[data-testid="stSidebar"] {{ background: {INDIGO}; }}
section[data-testid="stSidebar"] * {{ color: #F3F3FF; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a {{
  border-radius: 12px; padding: 6px 10px; margin: 2px 4px;
}}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {{ background: rgba(255,255,255,.12); }}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {{
  background: rgba(255,255,255,.95);
}}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] * {{ color: {INDIGO} !important; }}
section[data-testid="stSidebar"] input, section[data-testid="stSidebar"] [data-baseweb="select"] > div,
section[data-testid="stSidebar"] [data-baseweb="input"] {{
  background: rgba(255,255,255,.14) !important; border-color: rgba(255,255,255,.25) !important;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] > div,
section[data-testid="stSidebar"] .stSelectbox input, section[data-testid="stSidebar"] .stDateInput input {{
  background: #fff !important; color: {INK} !important; -webkit-text-fill-color: {INK} !important; }}
section[data-testid="stSidebar"] .stSelectbox svg {{ color: {INK} !important; }}
section[data-testid="stSidebar"] [data-baseweb="select"] * {{ color: {INK} !important; }}
div[class*="st-key-cal_"] button {{ background: transparent !important; color: {ORANGE} !important; font-size: 1.3rem; padding: 0 .4rem; min-height: 0; }}
div[class*="st-key-cal_"] button:disabled {{ color: #D5D7EA !important; }}
section[data-testid="stSidebar"] [data-testid="stLogo"] {{ height: 2.6rem; max-width: 100%; }}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {{
  background: rgba(255,255,255,.10); border: 1px dashed rgba(255,255,255,.4);
}}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {{ background: #fff; }}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button * {{ color: {INDIGO} !important; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] details {{
  border: 1px solid rgba(255,255,255,.25); border-radius: 12px; background: rgba(255,255,255,.06);
}}
section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.2); }}

/* Cards: any container whose key starts with "card" */
div[class*="st-key-card"] {{
  background: {CARD}; border-radius: 20px; padding: 18px 20px 14px 20px;
  box-shadow: 0 6px 22px rgba(80, 86, 170, .08);
}}
div[class*="st-key-card"] [data-testid="stPlotlyChart"] {{ margin-bottom: -6px; }}
.stPlotlyChart .main-svg {{ background: transparent !important; }}

.stMarkdown p.card-title, .card-title {{ font-size: .95rem !important; font-weight: 600; color: {INK}; margin: 0; line-height: 1.3; }}
.stMarkdown p.card-sub, .card-sub {{ font-size: .76rem !important; color: {MUTED}; margin: 2px 0 6px 0 !important; line-height: 1.35; }}
.pill {{
  display: inline-block; font-size: .7rem; color: {MUTED}; border: 1px solid #E1E3F2;
  border-radius: 999px; padding: 1px 10px; float: right; margin-top: 2px;
}}

/* KPI stack (big number with arrow) */
.kpi {{ display: flex; align-items: baseline; gap: 10px; margin: 8px 0 0 0; }}
.kpi .arrow {{ font-size: 1.6rem; font-weight: 700; line-height: 1; }}
.kpi .val {{ font-size: 1.75rem; font-weight: 600; color: {INK}; line-height: 1.1; }}
.kpi-note {{ font-size: .74rem; color: {MUTED}; margin: 2px 0 12px 30px; }}
.kpi-note b {{ font-weight: 600; }}
.up {{ color: {INDIGO}; }} .down {{ color: {ORANGE}; }}

/* Small stat tiles */
.tile {{ background: {CARD}; border-radius: 18px; padding: 14px 18px; box-shadow: 0 6px 22px rgba(80,86,170,.08); }}
.tile .lbl {{ font-size: .74rem; color: {MUTED}; }}
.tile .num {{ font-size: 1.45rem; font-weight: 600; color: {INK}; line-height: 1.25; }}
.tile .dlt {{ font-size: .74rem; font-weight: 500; }}
.dlt.pos {{ color: {GOOD}; }} .dlt.neg {{ color: {BAD}; }}

/* Progress bars */
.pbar {{ margin: 8px 0 10px 0; }}
.pbar .row {{ display: flex; justify-content: space-between; font-size: .76rem; color: {MUTED}; margin-bottom: 4px; }}
.pbar .track {{ height: 7px; background: {LAVENDER_SOFT}; border-radius: 99px; overflow: hidden; }}
.pbar .fill {{ height: 100%; border-radius: 99px; }}

/* Segmented bar */
.seg {{ display: flex; height: 9px; border-radius: 99px; overflow: hidden; margin: 12px 0 8px 0; }}
.legend {{ font-size: .72rem; color: {MUTED}; display: flex; gap: 14px; flex-wrap: wrap; }}
.legend i {{ display: inline-block; width: 10px; height: 6px; border-radius: 3px; margin-right: 5px; vertical-align: middle; }}

/* Calendar */
.cal-head {{ display: flex; justify-content: center; align-items: center; gap: 14px; font-weight: 500; font-size: .92rem; margin-bottom: 6px; }}
.cal-head span.nav {{ color: {ORANGE}; font-weight: 600; }}
table.cal, table.cal tr, table.cal td, table.cal th {{ border: none !important; background: transparent !important; padding: 0 !important; }}
table.cal {{ width: 100%; border-collapse: separate; border-spacing: 2px 4px; text-align: center; }}
table.cal th {{ font-size: .72rem; color: {MUTED}; font-weight: 500; }}
table.cal td {{ font-size: .78rem; color: {INK}; height: 28px; position: relative; }}
table.cal td .d {{ display: inline-flex; width: 28px; height: 28px; border-radius: 50%; align-items: center; justify-content: center; }}
table.cal td .d.best {{ border: 1.6px solid {ORANGE}; color: {ORANGE}; font-weight: 600; }}
table.cal td .d.worst {{ border: 1.6px solid {INDIGO}; color: {INDIGO}; font-weight: 600; }}
table.cal td .d.closed {{ color: #C6C8DA; }}
table.cal td .bar {{ position: absolute; left: 22%; right: 22%; bottom: -2px; height: 3px; border-radius: 2px; background: {LAVENDER}; }}

/* Chat (AI analyst / expense capture) */
.bubble-q {{ background: {INDIGO}; color: #fff; padding: 10px 14px; border-radius: 16px 16px 4px 16px; display: inline-block; max-width: 85%; font-size: .9rem; }}
.bubble-a {{ background: #F3F4FD; color: {INK}; padding: 12px 16px; border-radius: 16px 16px 16px 4px; font-size: .9rem; }}
.trace {{ font-size: .72rem; color: {MUTED}; border-top: 1px dashed #DADCF0; margin-top: 10px; padding-top: 8px; font-family: ui-monospace, Menlo, monospace !important; }}
.chip {{ display: inline-block; background: #F3F4FD; color: {INDIGO}; border-radius: 999px; padding: 4px 12px; font-size: .78rem; margin: 2px 4px 2px 0; }}
.badge {{ display: inline-block; border-radius: 999px; padding: 1px 9px; font-size: .7rem; font-weight: 500; }}
.badge.est {{ background: #FFF1E7; color: {ORANGE}; }}
.badge.conf {{ background: #ECECFD; color: {INDIGO}; }}
.badge.doc {{ background: #E6F5EE; color: {GOOD}; }}

/* Page header */
.page-h {{ display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 6px; }}
.page-h h1 {{ font-size: 1.55rem; margin: 0; padding: 0; }}
.page-h .sub {{ color: {MUTED}; font-size: .82rem; }}

/* Buttons */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
  border-radius: 999px; border: none; background: {INDIGO}; color: #fff; font-weight: 500; padding: .35rem 1.2rem;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{ background: {INDIGO_DARK}; color: #fff; }}
.stButton > button[kind="secondary"] {{ background: #EEF0FD; color: {INDIGO}; }}
[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; }}
div[data-baseweb="tab-list"] {{ gap: 6px; }}
button[data-baseweb="tab"] {{ border-radius: 999px; padding: 4px 14px; background: #fff; }}
button[data-baseweb="tab"][aria-selected="true"] {{ background: {INDIGO}; color: #fff; }}
div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] {{ display: none; }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _template() -> go.layout.Template:
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family="Poppins, system-ui, sans-serif", color=INK, size=11),
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        colorway=SERIES,
        margin=dict(l=4, r=4, t=8, b=4),
        xaxis=dict(showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED, size=10), ticks="", zeroline=False, automargin=True),
        yaxis=dict(gridcolor=GRID, automargin=True, linecolor="rgba(0,0,0,0)", tickfont=dict(color=MUTED, size=10), zeroline=False),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5,
                    font=dict(color=MUTED, size=10), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#fff", bordercolor="#E1E3F2", font=dict(color=INK, family="Poppins")),
        bargap=0.35,
    )
    return t


pio.templates["databased"] = _template()
pio.templates.default = "databased"

CHART_CFG = {"displayModeBar": False}


def chart(fig: go.Figure, height: int = 260, key: str | None = None) -> None:
    fig.update_layout(height=height, template=pio.templates["databased"], paper_bgcolor=CARD, plot_bgcolor=CARD)
    st.plotly_chart(fig, width="stretch", config=CHART_CFG, key=key, theme=None)


# HTML snippets ----------------------------------------------------------------
def esc(s: object) -> str:
    return html.escape(str(s))


def card_header(title: str, sub: str = "", pill: str = "") -> None:
    p = f'<span class="pill">{esc(pill)}</span>' if pill else ""
    s = f'<p class="card-sub">{esc(sub)}</p>' if sub else '<div style="height:6px"></div>'
    st.markdown(f'<p class="card-title">{esc(title)}{p}</p>{s}', unsafe_allow_html=True)


def page_header(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="page-h"><h1>{esc(title)}</h1><span class="sub">{esc(sub)}</span></div>',
                unsafe_allow_html=True)


def kpi_block(value: str, delta_pct: float | None, note: str) -> str:
    if delta_pct is None:
        arrow, cls = "•", "up"
    else:
        arrow, cls = ("↑", "up") if delta_pct >= 0 else ("↓", "down")
    d = f"<b class='{cls}'>{delta_pct:+.1f}%</b> " if delta_pct is not None else ""
    return (f'<div class="kpi"><span class="arrow {cls}">{arrow}</span><span class="val">{esc(value)}</span></div>'
            f'<div class="kpi-note">{d}{esc(note)}</div>')


def tile(label: str, value: str, delta: str | None = None, positive: bool | None = None) -> str:
    d = ""
    if delta:
        cls = "pos" if positive else "neg" if positive is not None else ""
        d = f'<div class="dlt {cls}">{esc(delta)}</div>'
    return f'<div class="tile"><div class="lbl">{esc(label)}</div><div class="num">{esc(value)}</div>{d}</div>'


def tiles(items: list[str]) -> None:
    cols = st.columns(len(items))
    for c, h in zip(cols, items):
        c.markdown(h, unsafe_allow_html=True)


def progress_bars(rows: list[tuple[str, float, str]], colors: list[str] | None = None) -> str:
    """rows: (label, fraction 0..1, right-hand text)."""
    colors = colors or [INDIGO, ORANGE, LAVENDER, PEACH]
    out = []
    for i, (lbl, frac, txt) in enumerate(rows):
        c = colors[i % len(colors)]
        out.append(
            f'<div class="pbar"><div class="row"><span>{esc(lbl)}</span><span>{esc(txt)}</span></div>'
            f'<div class="track"><div class="fill" style="width:{max(0, min(1, frac)) * 100:.1f}%;background:{c}"></div></div></div>'
        )
    return "".join(out)


def segmented(parts: list[tuple[str, float]], colors: list[str] | None = None) -> str:
    colors = colors or [INDIGO, LAVENDER, ORANGE, PEACH, "#C9CBE0"]
    total = sum(v for _, v in parts) or 1
    segs = "".join(f'<div style="width:{v / total * 100:.2f}%;background:{colors[i % len(colors)]}"></div>'
                   for i, (_, v) in enumerate(parts))
    leg = "".join(f'<span><i style="background:{colors[i % len(colors)]}"></i>{esc(n)} {v / total * 100:.0f}%</span>'
                  for i, (n, v) in enumerate(parts))
    return f'<div class="seg">{segs}</div><div class="legend">{leg}</div>'


def money(x: float, decimals: int = 0) -> str:
    if x is None:
        return "–"
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.{decimals}f}"


def pct(a: float, b: float) -> float | None:
    if b is None or b == 0 or a is None:
        return None
    return (a - b) / abs(b) * 100
