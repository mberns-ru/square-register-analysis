"""Public Terms of Service and Privacy Policy pages (readable without signing in)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import theme as T

DOCS = Path(__file__).resolve().parent.parent / "docs" / "legal"


def _render(filename: str) -> None:
    st.markdown("""<style>
.block-container { max-width: 860px !important; }
div.st-key-card_legal h1 { font-size: 1.7rem; margin-bottom: .2rem; }
div.st-key-card_legal h2 { font-size: 1.05rem; margin: 1.4rem 0 .3rem 0; }
div.st-key-card_legal p, div.st-key-card_legal li { font-size: .92rem; line-height: 1.6; }
</style>""", unsafe_allow_html=True)
    pages = st.session_state.get("_legal_pages", {})
    with st.container(key="card_legal"):
        if "home" in pages:
            st.page_link(pages["home"], label="Back to Databased", icon=":material/arrow_back:")
        # The policy text lives in docs/legal so it's also readable on GitHub.
        text = (DOCS / filename).read_text(encoding="utf-8")
        st.markdown(text.replace("$", "\\$"))
        other = "terms" if filename == "privacy.md" else "privacy"
        if other in pages:
            st.divider()
            st.page_link(pages[other], label="Terms of Service" if other == "terms" else "Privacy Policy",
                         icon=":material/description:")


def render_privacy() -> None:
    _render("privacy.md")


def render_terms() -> None:
    _render("terms.md")


def footer_links() -> None:
    """Small 'Terms · Privacy' links, for the sign-in page."""
    pages = st.session_state.get("_legal_pages", {})
    if not pages:
        return
    st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)
    with st.container(key="legal_links", horizontal=True, horizontal_alignment="center", gap="small"):
        st.page_link(pages["terms"], label="Terms of Service")
        st.markdown(f'<span style="color:{T.MUTED}">·</span>', unsafe_allow_html=True)
        st.page_link(pages["privacy"], label="Privacy Policy")
