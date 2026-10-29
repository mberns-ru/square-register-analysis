"""Settings: color scheme."""

from __future__ import annotations

import re

import plotly.graph_objects as go
import streamlit as st

from core import theme as T

HEX = re.compile(r"^#?[0-9A-Fa-f]{6}$")
FIELDS = [("primary", "Primary", "Sidebar highlights, buttons, main chart series"),
          ("accent", "Accent", "Second chart series, best days, warnings"),
          ("canvas", "Background", "The page behind the cards"),
          ("sidebar", "Sidebar", "The navigation rail")]


def apply_query_params() -> None:
    """Apply a scheme passed in the URL (?theme=Ocean, or ?theme=custom&primary=1F6FB2&...) once per session."""
    if st.session_state.get("_theme_from_url_done"):
        return
    st.session_state._theme_from_url_done = True
    qp = st.query_params
    name = qp.get("theme")
    if not name:
        return
    match = next((p for p in T.PRESETS if p.lower() == name.lower()), None)
    if match:
        set_scheme(match, **T.PRESETS[match])
    elif name.lower() == "custom":
        vals = {k: qp.get(k, "") for k, _, _ in FIELDS}
        if all(HEX.match(v or "") for v in vals.values()):
            set_scheme("Custom", **{k: "#" + v.lstrip("#").upper() for k, v in vals.items()})


def set_scheme(preset: str, primary: str, accent: str, canvas: str, sidebar: str) -> None:
    st.session_state.color_scheme = {"preset": preset, "primary": primary, "accent": accent,
                                     "canvas": canvas, "sidebar": sidebar}


def _share_query(cfg: dict) -> str:
    if cfg["preset"] in T.PRESETS:
        return f"?theme={cfg['preset'].lower()}"
    return "?theme=custom&" + "&".join(f"{k}={cfg[k].lstrip('#')}" for k, _, _ in FIELDS)


def _swatches(cfg: dict) -> str:
    dots = "".join(f'<span style="display:inline-block;width:22px;height:22px;border-radius:50%;'
                   f'background:{cfg[k]};border:2px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.08);'
                   f'margin-right:-6px"></span>' for k in ("sidebar", "primary", "accent", "canvas"))
    return f'<div style="margin:4px 0 10px 0">{dots}</div>'


def render(ctx=None) -> None:
    T.page_header("Settings", "Personalize how the dashboard looks")
    cur = T.scheme()

    with st.container(key="card_schemes"):
        T.card_header("Color scheme", "Pick a preset. Changes apply right away across every page.")
        cols = st.columns(len(T.PRESETS))
        for col, (name, cfg) in zip(cols, T.PRESETS.items()):
            with col, st.container(key=f"scheme_{name}"):
                active = cur["preset"] == name
                st.markdown(f'<div style="font-weight:600;font-size:.9rem">{name}'
                            f'{" <span class=badge style=background:" + T.TINT + ";color:" + T.INDIGO + ">current</span>" if active else ""}'
                            f'</div>{_swatches(cfg)}', unsafe_allow_html=True)
                if st.button("In use" if active else "Use", key=f"use_{name}", width="stretch",
                             type="primary" if active else "secondary", disabled=active):
                    set_scheme(name, **cfg)
                    st.rerun()

    left, right = st.columns([1, 1.15], gap="medium")
    with left, st.container(key="card_custom"):
        T.card_header("Custom colors", "Start from the current scheme and adjust any color")
        picked = {}
        c1, c2 = st.columns(2)
        for i, (k, label, help_) in enumerate(FIELDS):
            picked[k] = (c1 if i % 2 == 0 else c2).color_picker(label, cur[k], key=f"pick_{k}_{cur['preset']}",
                                                                help=help_)
        changed = any(picked[k].upper() != cur[k].upper() for k, _, _ in FIELDS)
        b1, b2 = st.columns(2)
        if b1.button("Apply custom colors", width="stretch", disabled=not changed):
            set_scheme("Custom", **{k: v.upper() for k, v in picked.items()})
            st.rerun()
        if b2.button("Reset to default", type="secondary", width="stretch",
                     disabled=cur["preset"] == T.DEFAULT_PRESET):
            set_scheme(T.DEFAULT_PRESET, **T.PRESETS[T.DEFAULT_PRESET])
            st.rerun()
        if T.luminance(picked["sidebar"]) > 0.45:
            st.caption("Light sidebar: navigation text switches to dark automatically.")

        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
        T.card_header("Keep or share this scheme",
                      "Colors are saved for this browser session. To keep them, bookmark the app with this "
                      "added to the end of its address:")
        st.code(_share_query(cur), language=None)

    with right, st.container(key="card_preview"):
        T.card_header("Preview", "How cards and charts look with the current scheme", pill=cur["preset"])
        a, b = st.columns(2)
        with a:
            st.markdown(T.kpi_block("$24,746", 6.2, "net sales vs last month")
                        + T.kpi_block("2,190", -3.1, "transactions"), unsafe_allow_html=True)
        with b:
            st.markdown(T.progress_bars([("Cold Beverages", 1, "25%"), ("Lunch", .84, "21%"),
                                         ("Breakfast", .82, "21%")]), unsafe_allow_html=True)
        fig = go.Figure()
        x = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        fig.add_bar(x=x, y=[620, 700, 680, 720, 860, 930, 810], name="This period",
                    marker=dict(color=T.INDIGO, cornerradius=3))
        fig.add_bar(x=x, y=[590, 650, 700, 690, 800, 880, 760], name="Prior period",
                    marker=dict(color=T.PEACH, cornerradius=3))
        fig.add_scatter(x=x, y=[600, 680, 690, 705, 830, 905, 790], name="Trend", mode="lines",
                        line=dict(color=T.ORANGE, width=2.4, shape="spline"))
        fig.update_layout(barmode="group", bargap=0.3)
        fig.update_yaxes(tickprefix="$")
        T.chart(fig, 230, key="settings_preview")
        st.markdown(T.segmented([("For Here", 77), ("Not set", 11), ("To Go", 9), ("Other", 3)]),
                    unsafe_allow_html=True)
