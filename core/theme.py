"""Visual theme: soft lavender canvas, white rounded cards, indigo + orange accents."""

from __future__ import annotations

import html
import tempfile
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

# Palette ---------------------------------------------------------------------
# Colors are per browser session (users can change them on the Settings page), so the uppercase names below
# (T.INDIGO, T.ORANGE, ...) are resolved on access by the module-level __getattr__ at the bottom of this file.
# INDIGO is the primary color and ORANGE the accent, whatever hue the chosen scheme uses.

PRESETS: dict[str, dict[str, str]] = {
    "Lavender": {"primary": "#5B5BD6", "accent": "#EE8A4E", "canvas": "#E6EAFB", "sidebar": "#5B5BD6"},
    "Ocean": {"primary": "#1F6FB2", "accent": "#20A99B", "canvas": "#E3EDF6", "sidebar": "#17507F"},
    "Forest": {"primary": "#2F7D5B", "accent": "#E0A33B", "canvas": "#E7EFE9", "sidebar": "#245F45"},
    "Sunset": {"primary": "#D2475E", "accent": "#F0A03C", "canvas": "#FBECE8", "sidebar": "#B23A4F"},
    "Plum": {"primary": "#7B3FA0", "accent": "#E4718F", "canvas": "#F0E8F6", "sidebar": "#6A3290"},
    "Graphite": {"primary": "#3D4451", "accent": "#3E86F5", "canvas": "#ECEEF1", "sidebar": "#2A2F38"},
}
DEFAULT_PRESET = "Lavender"


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb)


def mix(a: str, b: str, t: float) -> str:
    """Blend color a toward b by t (0 = a, 1 = b)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex([x + (y - x) * t for x, y in zip(ra, rb)])


def rgba(h: str, alpha: float) -> str:
    r, g, b = _rgb(h)
    return f"rgba({r},{g},{b},{alpha})"


def luminance(h: str) -> float:
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def build_palette(primary: str, accent: str, canvas: str, sidebar: str) -> dict:
    p = {
        "INDIGO": primary,
        "INDIGO_DARK": mix(primary, "#000000", 0.15),
        "LAVENDER": mix(primary, "#FFFFFF", 0.5),
        "LAVENDER_SOFT": mix(primary, "#FFFFFF", 0.82),
        "TINT": mix(primary, "#FFFFFF", 0.93),
        "ORANGE": accent,
        "PEACH": mix(accent, "#FFFFFF", 0.45),
        "ACCENT_TINT": mix(accent, "#FFFFFF", 0.9),
        "CANVAS": canvas,
        "CARD": "#FFFFFF",
        "INK": mix(primary, "#1A1A1A", 0.8),
        "MUTED": mix(primary, "#8A8A8A", 0.8),
        "GRID": mix(primary, "#FFFFFF", 0.91),
        "LINE": mix(primary, "#FFFFFF", 0.82),
        "NEUTRAL": mix(mix(primary, "#888888", 0.7), "#FFFFFF", 0.55),
        "GOOD": "#3BA776",
        "BAD": "#E0644A",
        "SIDEBAR": sidebar,
    }
    light_sidebar = luminance(sidebar) > 0.45
    p["SB_TEXT"] = p["INK"] if light_sidebar else "#F6F6FF"
    p["SB_ACTIVE_BG"] = primary if light_sidebar else "rgba(255,255,255,.95)"
    p["SB_ACTIVE_TEXT"] = "#FFFFFF" if light_sidebar else (primary if luminance(primary) < 0.6 else p["INK"])
    p["SB_HOVER"] = "rgba(0,0,0,.06)" if light_sidebar else "rgba(255,255,255,.12)"
    p["SB_LINE"] = "rgba(0,0,0,.15)" if light_sidebar else "rgba(255,255,255,.25)"
    p["SERIES"] = [primary, accent, p["LAVENDER"], p["PEACH"], "#7FC8C2", "#C9A4E6", "#9AA0B8"]
    return p


def scheme() -> dict:
    """The current session's color settings: preset name + four base colors."""
    try:
        cfg = st.session_state.get("color_scheme")
    except Exception:  # noqa: BLE001  (outside a Streamlit run)
        cfg = None
    return cfg or {"preset": DEFAULT_PRESET, **PRESETS[DEFAULT_PRESET]}


def palette() -> dict:
    cfg = scheme()
    key = (cfg["primary"], cfg["accent"], cfg["canvas"], cfg["sidebar"])
    cache = _PALETTE_CACHE.get(key)
    if cache is None:
        cache = _PALETTE_CACHE[key] = build_palette(*key)
    return cache


_PALETTE_CACHE: dict[tuple, dict] = {}


def __getattr__(name: str):
    pal = palette()
    if name in pal:
        return pal[name]
    raise AttributeError(name)


def css() -> str:
    c = palette()
    INDIGO, INDIGO_DARK, LAVENDER, LAVENDER_SOFT, ORANGE = (c[k] for k in
                                                            ("INDIGO", "INDIGO_DARK", "LAVENDER", "LAVENDER_SOFT", "ORANGE"))
    CANVAS, CARD, INK, MUTED, GOOD, BAD = (c[k] for k in ("CANVAS", "CARD", "INK", "MUTED", "GOOD", "BAD"))
    TINT, LINE, SIDEBAR, ACCENT_TINT = c["TINT"], c["LINE"], c["SIDEBAR"], c["ACCENT_TINT"]
    SB_TEXT, SB_ACTIVE_BG, SB_ACTIVE_TEXT, SB_HOVER, SB_LINE = (c[k] for k in
                                                                ("SB_TEXT", "SB_ACTIVE_BG", "SB_ACTIVE_TEXT", "SB_HOVER", "SB_LINE"))
    SHADOW = rgba(INDIGO, 0.08)
    return f"""
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
section[data-testid="stSidebar"] {{ background: {SIDEBAR}; }}
section[data-testid="stSidebar"] * {{ color: {SB_TEXT}; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a {{
  border-radius: 12px; padding: 6px 10px; margin: 2px 4px;
}}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {{ background: {SB_HOVER}; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {{
  background: {SB_ACTIVE_BG};
}}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] * {{ color: {SB_ACTIVE_TEXT} !important; }}
section[data-testid="stSidebar"] input, section[data-testid="stSidebar"] [data-baseweb="select"] > div,
section[data-testid="stSidebar"] [data-baseweb="input"] {{
  background: rgba(255,255,255,.14) !important; border-color: {SB_LINE} !important;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] > div,
section[data-testid="stSidebar"] .stSelectbox input, section[data-testid="stSidebar"] .stDateInput input {{
  background: #fff !important; color: {INK} !important; -webkit-text-fill-color: {INK} !important; }}
section[data-testid="stSidebar"] .stSelectbox svg {{ color: {INK} !important; }}
section[data-testid="stSidebar"] [data-baseweb="select"] * {{ color: {INK} !important; }}
div[class*="st-key-cal_"] button {{ background: transparent !important; color: {ORANGE} !important; font-size: 1.3rem; padding: 0 .4rem; min-height: 0; }}
div[class*="st-key-cal_"] button:disabled {{ color: {LINE} !important; }}
section[data-testid="stSidebar"] [data-testid="stLogo"] {{ height: 2.6rem; max-width: 100%; }}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {{
  background: rgba(255,255,255,.10); border: 1px dashed {SB_LINE};
}}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {{ background: #fff; }}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button * {{ color: {INDIGO} !important; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] details {{
  border: 1px solid {SB_LINE}; border-radius: 12px; background: rgba(255,255,255,.06);
}}
section[data-testid="stSidebar"] hr {{ border-color: {SB_LINE}; }}

/* Cards: any container whose key starts with "card" */
div[class*="st-key-card"] {{
  background: {CARD}; border-radius: 20px; padding: 18px 20px 14px 20px;
  box-shadow: 0 6px 22px {SHADOW};
}}
div[class*="st-key-card"] [data-testid="stPlotlyChart"] {{ margin-bottom: -6px; }}
div[class*="st-key-ans_"] {{ background: {TINT}; border-radius: 16px; padding: 14px 18px; }}
div[class*="st-key-ans_"] .stPlotlyChart .main-svg {{ background: transparent !important; }}
section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
  background: rgba(255,255,255,.14) !important; border: 1px solid {SB_LINE} !important; }}
section[data-testid="stSidebar"] .stButton > button[kind="secondary"] * {{ color: {SB_TEXT} !important; }}
div.st-key-sb_account {{ background: rgba(255,255,255,.10); border: 1px solid {SB_LINE}; border-radius: 14px; padding: 12px; }}
div.st-key-google_btn a, div.st-key-google_btn button {{ border: 1px solid {LINE} !important; border-radius: 999px !important;
  background-color: #fff !important; padding: 9px 16px 9px 44px !important; position: relative; }}
div.st-key-google_btn a:hover, div.st-key-google_btn button:hover {{ background-color: {TINT} !important; border-color: {LAVENDER} !important; }}
div.st-key-google_btn a p, div.st-key-google_btn button p {{ color: {INK} !important; font-weight: 500; font-size: .92rem; }}
.or-divider {{ display: flex; align-items: center; gap: 10px; color: {MUTED}; font-size: .74rem; margin: 14px 0 4px 0; }}
.or-divider::before, .or-divider::after {{ content: ""; flex: 1; height: 1px; background: {LINE}; }}
div.st-key-card_auth {{ padding: 30px 32px 24px 32px; min-height: 560px; }}
div.st-key-card_auth .stTextInput label p, div.st-key-card_firstbiz .stTextInput label p {{ font-size: .8rem; color: {MUTED}; }}
.stButton > button[kind="tertiary"] {{ background: transparent !important; color: {INDIGO} !important; padding: 0; }}
div.st-key-card_analyst {{ border-top: 4px solid {INDIGO}; margin-bottom: 8px; }}
.stPlotlyChart .main-svg {{ background: transparent !important; }}

.stMarkdown p.card-title, .card-title {{ font-size: .95rem !important; font-weight: 600; color: {INK}; margin: 0; line-height: 1.3; }}
.stMarkdown p.card-sub, .card-sub {{ font-size: .76rem !important; color: {MUTED}; margin: 2px 0 6px 0 !important; line-height: 1.35; }}
.pill {{
  display: inline-block; font-size: .7rem; color: {MUTED}; border: 1px solid {LINE};
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
.tile {{ background: {CARD}; border-radius: 18px; padding: 14px 18px; box-shadow: 0 6px 22px {SHADOW}; }}
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
table.cal td .d.closed {{ color: {LINE}; }}
table.cal td .bar {{ position: absolute; left: 22%; right: 22%; bottom: -2px; height: 3px; border-radius: 2px; background: {LAVENDER}; }}

/* Chat (AI analyst / expense capture) */
.bubble-q {{ background: {INDIGO}; color: #fff; padding: 10px 14px; border-radius: 16px 16px 4px 16px; display: inline-block; max-width: 85%; font-size: .9rem; }}
.bubble-a {{ background: {TINT}; color: {INK}; padding: 12px 16px; border-radius: 16px 16px 16px 4px; font-size: .9rem; }}
.trace {{ font-size: .72rem; color: {MUTED}; border-top: 1px dashed {LINE}; margin-top: 10px; padding-top: 8px; font-family: ui-monospace, Menlo, monospace !important; }}
.chip {{ display: inline-block; background: {TINT}; color: {INDIGO}; border-radius: 999px; padding: 4px 12px; font-size: .78rem; margin: 2px 4px 2px 0; }}
.badge {{ display: inline-block; border-radius: 999px; padding: 1px 9px; font-size: .7rem; font-weight: 500; }}
.badge.est {{ background: {ACCENT_TINT}; color: {ORANGE}; }}
.badge.conf {{ background: {TINT}; color: {INDIGO}; }}
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
.stButton > button[kind="secondary"] {{ background: {TINT}; color: {INDIGO}; }}
[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; }}
div[data-baseweb="tab-list"] {{ gap: 6px; }}
button[data-baseweb="tab"] {{ border-radius: 999px; padding: 4px 14px; background: #fff; }}
button[data-baseweb="tab"][aria-selected="true"] {{ background: {INDIGO}; color: #fff; }}
div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] {{ display: none; }}
/* Recolor native widgets that otherwise use the config.toml primary color */
span[data-baseweb="tag"] {{ background: {INDIGO} !important; }}
div[role="slider"] {{ background: {INDIGO} !important; }}
div[data-testid="stSliderThumbValue"] {{ color: {SB_TEXT} !important; }}
button[kind="segmented_controlActive"] {{ background: {TINT} !important; border-color: {INDIGO} !important; color: {INDIGO} !important; }}
button[kind="segmented_controlActive"] * {{ color: {INDIGO} !important; }}
[data-testid="stChatInput"] button {{ background: {INDIGO} !important; }}
[data-testid="stMain"] [data-testid="stChatInput"] > div, [data-testid="stMain"] [data-baseweb="input"], [data-testid="stMain"] [data-baseweb="textarea"],
[data-testid="stMain"] [data-baseweb="base-input"], [data-testid="stMain"] [data-testid="stFileUploaderDropzone"],
[data-testid="stMain"] [data-baseweb="select"] > div {{ background: {TINT} !important; }}
[data-testid="stChatInput"] button svg {{ color: #fff !important; fill: #fff !important; }}
</style>
"""


def inject() -> None:
    st.markdown(css(), unsafe_allow_html=True)


def template() -> go.layout.Template:
    c = palette()
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family="Poppins, system-ui, sans-serif", color=c["INK"], size=11),
        paper_bgcolor=c["CARD"],
        plot_bgcolor=c["CARD"],
        colorway=c["SERIES"],
        margin=dict(l=4, r=4, t=8, b=4),
        xaxis=dict(showgrid=False, linecolor=c["GRID"], tickfont=dict(color=c["MUTED"], size=10), ticks="",
                   zeroline=False, automargin=True),
        yaxis=dict(gridcolor=c["GRID"], automargin=True, linecolor="rgba(0,0,0,0)",
                   tickfont=dict(color=c["MUTED"], size=10), zeroline=False),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5,
                    font=dict(color=c["MUTED"], size=10), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#fff", bordercolor=c["LINE"], font=dict(color=c["INK"], family="Poppins")),
        bargap=0.35,
    )
    return t


CHART_CFG = {"displayModeBar": False}


def chart(fig: go.Figure, height: int = 260, key: str | None = None, bg: str | None = None) -> None:
    c = palette()
    bg = bg or c["CARD"]
    fig.update_layout(height=height, template=template(), paper_bgcolor=bg, plot_bgcolor=bg)
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
    c = palette()
    colors = colors or [c["INDIGO"], c["ORANGE"], c["LAVENDER"], c["PEACH"]]
    out = []
    for i, (lbl, frac, txt) in enumerate(rows):
        c = colors[i % len(colors)]
        out.append(
            f'<div class="pbar"><div class="row"><span>{esc(lbl)}</span><span>{esc(txt)}</span></div>'
            f'<div class="track"><div class="fill" style="width:{max(0, min(1, frac)) * 100:.1f}%;background:{c}"></div></div></div>'
        )
    return "".join(out)


def segmented(parts: list[tuple[str, float]], colors: list[str] | None = None) -> str:
    c = palette()
    colors = colors or [c["INDIGO"], c["LAVENDER"], c["ORANGE"], c["PEACH"], c["NEUTRAL"]]
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


def logo_files() -> tuple[str, str]:
    """Write the logo in the current colors (sidebar text color, primary monogram) and return file paths."""
    c = palette()
    folder = Path(tempfile.gettempdir()) / "databased-logos"
    folder.mkdir(exist_ok=True)
    tag = (c["INDIGO"] + c["SB_TEXT"] + c["SIDEBAR"]).replace("#", "")
    logo, icon = folder / f"logo-{tag}.svg", folder / f"icon-{tag}.svg"
    disc = "#FFFFFF" if c["SB_TEXT"].upper() != c["INK"].upper() else c["INDIGO"]
    mono = c["INDIGO"] if disc == "#FFFFFF" else "#FFFFFF"
    badge = (f'<circle cx="22" cy="22" r="20" fill="{disc}"/><text x="22" y="28" text-anchor="middle" '
             f'font-family="Poppins,Arial,sans-serif" font-weight="700" font-size="15" fill="{mono}">DB</text>')
    if not logo.exists():
        logo.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="44" viewBox="0 0 220 44">{badge}'
            f'<text x="52" y="21" font-family="Poppins,Arial,sans-serif" font-weight="600" font-size="18" '
            f'fill="{c["SB_TEXT"]}">Databased</text><text x="52" y="37" font-family="Poppins,Arial,sans-serif" '
            f'font-size="11" fill="{c["SB_TEXT"]}" fill-opacity=".75">Square sales analytics</text></svg>')
        icon.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44">'
                        f'{badge}</svg>')
    return str(logo), str(icon)
