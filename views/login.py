"""Sign in / create account / reset password, plus the first-business screen."""

from __future__ import annotations

import streamlit as st

from core import auth
from core import theme as T

MODES = {"signin": "Sign in", "signup": "Create account"}


def _hide_sidebar() -> None:
    st.markdown("""<style>
section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarNav"] { display: none !important; }
.block-container { max-width: 1120px !important; padding-top: 3.2rem !important; }
</style>""", unsafe_allow_html=True)


def _hero() -> None:
    c = T.palette()
    st.markdown(f"""
<div style="background: linear-gradient(150deg, {c['SIDEBAR']} 0%, {c['INDIGO']} 60%, {T.mix(c['INDIGO'], c['ORANGE'], .35)} 130%);
            border-radius: 24px; padding: 34px 34px 28px 34px; color: #fff; min-height: 560px; position: relative; overflow: hidden;">
  <div style="display:flex;align-items:center;gap:10px">
    <img src="{T.mark_data_uri()}" alt="" style="width:52px;height:52px;border-radius:14px;
         box-shadow:0 4px 14px rgba(0,0,0,.18)">
    <div><div style="font-weight:700;font-size:1.15rem;line-height:1.15">{T.APP_NAME}</div>
         <div style="font-size:.75rem;opacity:.8">by Databased</div></div>
  </div>
  <div style="font-size:2rem;font-weight:600;line-height:1.2;margin:56px 0 14px 0">Your Square sales,<br>finally explained.</div>
  <div style="opacity:.88;font-size:.95rem;max-width:400px">Upload your monthly exports and see sales, profit, refunds
    and forecasts in one place. Ask questions in plain language.</div>
  <div style="margin-top:34px;display:flex;flex-direction:column;gap:12px;font-size:.88rem">
    <div>✓&nbsp; Sales, expenses and profit in one view</div>
    <div>✓&nbsp; Items that sell well but earn little, flagged</div>
    <div>✓&nbsp; An AI analyst that shows its numbers</div>
  </div>
  <div style="position:absolute;left:34px;right:34px;bottom:28px;display:flex;gap:12px">
    <div style="flex:1;background:rgba(255,255,255,.14);border-radius:16px;padding:12px 14px">
      <div style="font-size:.7rem;opacity:.8">Net sales</div><div style="font-size:1.25rem;font-weight:600">↑ $18,240</div></div>
    <div style="flex:1;background:rgba(255,255,255,.14);border-radius:16px;padding:12px 14px">
      <div style="font-size:.7rem;opacity:.8">Best day</div><div style="font-size:1.25rem;font-weight:600">Sat</div></div>
    <div style="flex:1;background:rgba(255,255,255,.14);border-radius:16px;padding:12px 14px">
      <div style="font-size:.7rem;opacity:.8">Margin</div><div style="font-size:1.25rem;font-weight:600">18%</div></div>
  </div>
</div>""", unsafe_allow_html=True)


def _error(e: Exception) -> None:
    st.error(str(e), icon=":material/error:")


def _signin() -> None:
    with st.form("signin_form", border=False):
        email = st.text_input("Email", placeholder="you@yourcafe.com", key="si_email")
        pw = st.text_input("Password", type="password", key="si_pw")
        go = st.form_submit_button("Sign in", width="stretch")
    if go:
        try:
            with st.spinner("Signing in…"):
                auth.sign_in(email, pw)
            st.rerun()
        except auth.AuthError as e:
            _error(e)
    if st.button("Forgot your password?", type="tertiary", key="to_reset"):
        st.session_state.auth_mode = "reset"
        st.rerun()


def _signup() -> None:
    with st.form("signup_form", border=False):
        a, b = st.columns(2)
        name = a.text_input("Your name", placeholder="Sam Rivera", key="su_name")
        biz = b.text_input("Business name", placeholder="Maple Street Coffee", key="su_biz")
        email = st.text_input("Email", placeholder="you@yourcafe.com", key="su_email")
        a, b = st.columns(2)
        pw = a.text_input("Password", type="password", key="su_pw", help=f"At least {auth.MIN_PASSWORD} characters")
        pw2 = b.text_input("Confirm password", type="password", key="su_pw2")
        go = st.form_submit_button("Create account", width="stretch")
    if go:
        try:
            with st.spinner("Creating your account…"):
                acct = auth.sign_up(email, pw, pw2, name, biz)
            if acct is None:
                st.session_state.auth_notice = (f"Almost done! We sent a confirmation link to {email.strip()}. "
                                                f"Click it, then sign in here.")
                st.session_state.auth_mode = "signin"
                st.session_state.si_email = email.strip()
            st.rerun()
        except auth.AuthError as e:
            _error(e)
    st.markdown('<p class="card-sub" style="text-align:center;margin-top:6px">Your data is private to your '
                'business. Teammates can be added later.</p>',
                unsafe_allow_html=True)


def _reset() -> None:
    T.card_header("Reset your password", "We'll email you a 6-digit code.")
    sent = st.session_state.get("reset_sent_to")
    if not sent:
        with st.form("reset_send", border=False):
            email = st.text_input("Email", value=st.session_state.get("si_email", ""), key="rs_email")
            go = st.form_submit_button("Email me a code", width="stretch")
        if go:
            try:
                auth.send_reset_code(email)
                st.session_state.reset_sent_to = email.strip().lower()
                st.rerun()
            except auth.AuthError as e:
                _error(e)
    else:
        st.info(f"If {sent} has an account, a code is on its way.", icon=":material/mail:")
        with st.form("reset_verify", border=False):
            code = st.text_input("6-digit code", max_chars=10, key="rs_code")
            a, b = st.columns(2)
            pw = a.text_input("New password", type="password", key="rs_pw")
            pw2 = b.text_input("Confirm new password", type="password", key="rs_pw2")
            go = st.form_submit_button("Set new password and sign in", width="stretch")
        if go:
            try:
                auth.reset_password(sent, code, pw, pw2)
                st.session_state.pop("reset_sent_to", None)
                st.rerun()
            except auth.AuthError as e:
                _error(e)
    if st.button("← Back to sign in", type="tertiary", key="reset_back"):
        st.session_state.pop("reset_sent_to", None)
        st.session_state.auth_mode = "signin"
        st.rerun()


def render() -> None:
    _hide_sidebar()
    st.session_state.setdefault("auth_mode", "signin")
    left, right = st.columns([1.05, 1], gap="large")
    with left:
        _hero()
    with right, st.container(key="card_auth"):
        mode = st.session_state.auth_mode
        if mode == "reset":
            _reset()
            return
        st.markdown(f'<p style="font-size:1.45rem;font-weight:600;margin:4px 0 2px 0;color:{T.INK}">'
                    f'{"Welcome back" if mode == "signin" else "Create your account"}</p>'
                    f'<p class="card-sub" style="margin-bottom:14px">'
                    f'{"Sign in to see your dashboard." if mode == "signin" else "Set up your business in a minute."}'
                    f'</p>', unsafe_allow_html=True)
        def _switch():
            if st.session_state.auth_seg:  # clicking the selected option again clears it; ignore that
                st.session_state.auth_mode = st.session_state.auth_seg
        st.session_state.auth_seg = mode
        st.segmented_control("Mode", list(MODES), format_func=MODES.get, label_visibility="collapsed",
                             key="auth_seg", on_change=_switch, width="stretch")
        notice = st.session_state.pop("auth_notice", None)
        if notice:
            st.success(notice, icon=":material/mark_email_read:")
        _signin() if mode == "signin" else _signup()
    with right:
        from views import legal
        legal.footer_links()


def render_first_business() -> None:
    """Shown to a signed-in user who doesn't belong to any business yet."""
    _hide_sidebar()
    acct = auth.current()
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid, st.container(key="card_firstbiz"):
        T.card_header(f"Welcome{', ' + acct.full_name.split()[0] if acct.full_name else ''}!",
                      "Name your business to set up your dashboard.")
        with st.form("first_biz", border=False):
            name = st.text_input("Business name", placeholder="Maple Street Coffee")
            go = st.form_submit_button("Create business", width="stretch")
        if go:
            try:
                auth.create_business(name)
                st.rerun()
            except auth.AuthError as e:
                _error(e)
        from views import legal
        legal.footer_links()
        if st.button("Sign out", type="tertiary"):
            auth.sign_out()
            st.rerun()


def sidebar_account() -> None:
    """Account box in the sidebar: who's signed in, which business, sign out."""
    acct = auth.current()
    if acct is None:
        return
    with st.sidebar:
        st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)
        with st.container(key="sb_account"):
            initials = "".join(w[0] for w in (acct.full_name or acct.email).split()[:2]).upper()
            biz = acct.business
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px">'
                f'<div style="width:34px;height:34px;border-radius:50%;background:#fff;color:{T.INDIGO};'
                f'font-weight:600;display:flex;align-items:center;justify-content:center;font-size:.8rem">{T.esc(initials)}</div>'
                f'<div style="line-height:1.2;overflow:hidden"><div style="font-weight:600;font-size:.88rem">'
                f'{T.esc(acct.full_name or acct.email)}</div><div style="font-size:.72rem;opacity:.8">'
                f'{T.esc(biz["name"]) if biz else "No business yet"}{" · " + biz["role"] if biz else ""}</div></div></div>',
                unsafe_allow_html=True)
            if len(acct.businesses) > 1:
                ids = [b["business_id"] for b in acct.businesses]
                names = {b["business_id"]: b["name"] for b in acct.businesses}
                st.selectbox("Business", ids, format_func=names.get, key="business_id")
            if st.button("Sign out", key="sign_out", type="secondary", width="stretch", icon=":material/logout:"):
                auth.sign_out()
                st.rerun()
