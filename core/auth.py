"""Supabase authentication for the dashboard.

Configure with SUPABASE_URL and SUPABASE_ANON_KEY in .streamlit/secrets.toml (or environment variables).
When they are missing the app runs in local mode without accounts.

Each browser session gets its own Supabase client, so the signed-in user's token is used for every query and
row-level security in the database limits them to their own business.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import streamlit as st

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


def _setting(name: str) -> str | None:
    v = os.environ.get(name)
    if v:
        return v
    try:
        return st.secrets.get(name)  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001  (no secrets file)
        return None


def config() -> tuple[str, str] | None:
    url = _setting("SUPABASE_URL")
    key = _setting("SUPABASE_ANON_KEY") or _setting("SUPABASE_KEY")
    return (url, key) if url and key else None


def enabled() -> bool:
    return config() is not None


def _make_client(url: str, key: str):
    from supabase import ClientOptions, create_client

    return create_client(url, key, options=ClientOptions(auto_refresh_token=True, persist_session=False,
                                                      postgrest_client_timeout=30))


def client():
    """This session's Supabase client (carries the signed-in user's token)."""
    if "_sb" not in st.session_state:
        url, key = config()  # type: ignore[misc]
        st.session_state._sb = _make_client(url, key)
    return st.session_state._sb


@dataclass
class Account:
    user_id: str
    email: str
    full_name: str = ""
    businesses: list[dict] = field(default_factory=list)  # [{business_id, name, role}]

    @property
    def business(self) -> dict | None:
        bid = st.session_state.get("business_id")
        for b in self.businesses:
            if b["business_id"] == bid:
                return b
        return self.businesses[0] if self.businesses else None


class AuthError(Exception):
    pass


FRIENDLY = [
    (r"invalid login credentials", "That email and password don't match an account."),
    (r"email not confirmed", "Please confirm your email first. Check your inbox for the link."),
    (r"user already registered|already been registered", "An account with this email already exists. Try signing in."),
    (r"password should be at least|weak password", f"Choose a stronger password (at least {MIN_PASSWORD} characters)."),
    (r"rate limit|too many requests|security purposes", "Too many attempts. Please wait a minute and try again."),
    (r"token has expired|invalid.*(otp|token)", "That code is wrong or has expired. Request a new one."),
    (r"unable to validate email|invalid format", "Please enter a valid email address."),
    (r"connect|timed out|name or service|getaddrinfo|network", "Can't reach the account server. Check your connection and try again."),
]


def _friendly(e: Exception) -> AuthError:
    msg = str(getattr(e, "message", "") or e)
    for pat, text in FRIENDLY:
        if re.search(pat, msg, re.I):
            return AuthError(text)
    return AuthError(msg or "Something went wrong. Please try again.")


def _validate_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("Please enter a valid email address.")
    return email


# Actions ------------------------------------------------------------------------------------------------
def sign_in(email: str, password: str) -> Account:
    email = _validate_email(email)
    if not password:
        raise AuthError("Please enter your password.")
    try:
        res = client().auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:  # noqa: BLE001
        raise _friendly(e) from e
    return _start_session(res.user)


def sign_up(email: str, password: str, confirm: str, full_name: str, business_name: str) -> Account | None:
    """Returns the account if signed in right away, or None if Supabase asks the user to confirm their email."""
    email = _validate_email(email)
    if not full_name.strip():
        raise AuthError("Please enter your name.")
    if not business_name.strip():
        raise AuthError("Please enter your business name.")
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"Password must be at least {MIN_PASSWORD} characters.")
    if password != confirm:
        raise AuthError("Passwords don't match.")
    try:
        res = client().auth.sign_up({
            "email": email, "password": password,
            # read by the handle_new_user() trigger, which creates the profile and the business
            "options": {"data": {"full_name": full_name.strip(), "business_name": business_name.strip()}},
        })
    except Exception as e:  # noqa: BLE001
        raise _friendly(e) from e
    if res.user is not None and not (res.user.identities or []):
        # Supabase returns a user with no identities when the email is already registered
        raise AuthError("An account with this email already exists. Try signing in.")
    if res.session is None:
        return None
    return _start_session(res.user)


def send_reset_code(email: str) -> None:
    email = _validate_email(email)
    try:
        client().auth.reset_password_for_email(email)
    except Exception as e:  # noqa: BLE001
        raise _friendly(e) from e


def reset_password(email: str, code: str, new_password: str, confirm: str) -> Account:
    email = _validate_email(email)
    if len(new_password) < MIN_PASSWORD:
        raise AuthError(f"Password must be at least {MIN_PASSWORD} characters.")
    if new_password != confirm:
        raise AuthError("Passwords don't match.")
    try:
        res = client().auth.verify_otp({"email": email, "token": code.strip(), "type": "recovery"})
        client().auth.update_user({"password": new_password})
    except Exception as e:  # noqa: BLE001
        raise _friendly(e) from e
    return _start_session(res.user)


def sign_out() -> bool:
    """Sign out of Supabase (and Streamlit's Google login). Returns True when the browser is being redirected,
    in which case the caller must not st.rerun() (that would discard the redirect)."""
    try:
        client().auth.sign_out()
    except Exception:  # noqa: BLE001
        pass
    for k in ("_sb", "account", "business_id", "auth_mode", "analyst_log", "_google_bridge_failed"):
        st.session_state.pop(k, None)
    if streamlit_google_configured() and _streamlit_logged_in():
        st.logout()  # also clear Streamlit's Google login cookie, or the next run would sign straight back in
        return True
    return False


def create_business(name: str) -> None:
    acct = current()
    if not name.strip():
        raise AuthError("Please enter your business name.")
    try:
        client().table("businesses").insert({"name": name.strip(), "created_by": acct.user_id}).execute()
    except Exception as e:  # noqa: BLE001
        raise _friendly(e) from e
    refresh_businesses()


def refresh_businesses() -> None:
    acct = current()
    try:
        rows = (client().table("business_members")
                .select("role, businesses(business_id, name)")
                .eq("user_id", acct.user_id).execute().data) or []
    except Exception as e:  # noqa: BLE001
        raise _friendly(e) from e
    acct.businesses = sorted(
        [{"business_id": r["businesses"]["business_id"], "name": r["businesses"]["name"], "role": r["role"]}
         for r in rows if r.get("businesses")], key=lambda b: b["name"].lower())


def _start_session(user) -> Account:
    meta = getattr(user, "user_metadata", None) or {}
    acct = Account(user_id=str(user.id), email=user.email or "",
                   full_name=meta.get("full_name") or meta.get("name") or "")
    st.session_state.account = acct
    refresh_businesses()
    if acct.businesses and st.session_state.get("business_id") not in {b["business_id"] for b in acct.businesses}:
        st.session_state.business_id = acct.businesses[0]["business_id"]
    return acct


def current() -> Account | None:
    return st.session_state.get("account")


# Sign in with Google (OAuth, PKCE flow) --------------------------------------------------------------------
# Supabase sends the browser to Google and back to this app with ?code=...; that return trip starts a fresh
# Streamlit session, so the one-time PKCE verifier is kept server-side for a few minutes under a random flow ID
# that rides along in the return URL.
OAUTH_TTL = 600  # seconds


@st.cache_resource
def _pending_oauth() -> dict[str, tuple[str, float]]:
    return {}


@st.cache_data(ttl=300, show_spinner=False)
def _enabled_providers(url: str, key: str) -> dict:
    import httpx

    try:
        r = httpx.get(f"{url}/auth/v1/settings", headers={"apikey": key}, timeout=5)
        return r.json().get("external", {}) if r.status_code == 200 else {}
    except Exception:  # noqa: BLE001
        return {}


def streamlit_google_configured() -> bool:
    """True when [auth] / [auth.google] are in secrets, so Google sign-in runs through Streamlit's st.login."""
    try:
        a = st.secrets.get("auth")
        return bool(a and a.get("redirect_uri") and a.get("google"))
    except Exception:  # noqa: BLE001
        return False


def google_mode() -> str | None:
    """'streamlit' (consent screen shows the app's address), 'supabase' (shows the Supabase address) or None."""
    if not google_enabled():
        return None
    return "streamlit" if streamlit_google_configured() else "supabase"


def google_enabled() -> bool:
    """True once the Google provider is switched on in Supabase (Authentication → Sign In / Providers)."""
    if _setting("GOOGLE_SIGN_IN") in ("0", "false", "False"):
        return False
    cfg = config()
    return bool(cfg and _enabled_providers(*cfg).get("google"))


def app_url() -> str:
    """Where Google should send people back to. Set APP_URL in secrets to pin it (recommended when hosted)."""
    explicit = _setting("APP_URL")
    if explicit:
        return explicit.rstrip("/")
    try:
        parts = urlsplit(st.context.url)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    except Exception:  # noqa: BLE001
        pass
    return "http://localhost:8501"


def google_sign_in_url() -> str:
    """A fresh Google sign-in link for this browser session (reused until it expires)."""
    cached = st.session_state.get("_google_url")
    if cached and time.time() - cached[1] < OAUTH_TTL - 60:
        return cached[0]
    flow = secrets.token_urlsafe(18)
    c = client()
    res = c.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {"redirect_to": f"{app_url()}/?auth_flow={flow}",
                    "query_params": {"prompt": "select_account"}},
    })
    verifier = c.auth._storage.get_item(f"{c.auth._storage_key}-code-verifier")
    store = _pending_oauth()
    now = time.time()
    for k in [k for k, (_, t) in store.items() if now - t > OAUTH_TTL]:
        store.pop(k, None)
    store[flow] = (verifier, now)
    st.session_state._google_url = (res.url, now)
    return res.url


def finish_oauth_if_returning() -> None:
    """Call at the top of the app: completes a Google sign-in when the browser comes back with ?code=..."""
    qp = st.query_params
    flow = qp.get("auth_flow")
    if not flow or not ({"code", "error", "error_description"} & set(qp.keys())):
        return
    code = qp.get("code")
    err = qp.get("error_description") or qp.get("error")
    st.query_params.clear()
    entry = _pending_oauth().pop(flow, None)
    try:
        if err:
            raise AuthError("Google sign-in was cancelled." if "denied" in err.lower() else _friendly(Exception(err)).args[0])
        if entry is None or time.time() - entry[1] > OAUTH_TTL:
            raise AuthError("That Google sign-in link expired. Please try again.")
        res = client().auth.exchange_code_for_session(
            {"auth_code": code, "code_verifier": entry[0], "redirect_to": f"{app_url()}/?auth_flow={flow}"})
        _start_session(res.user)
    except AuthError as e:
        st.session_state.auth_error = str(e)
    except Exception as e:  # noqa: BLE001
        st.session_state.auth_error = str(_friendly(e))


# Sign in with Google through Streamlit (st.login) ---------------------------------------------------------------
# Google's consent screen names the address that receives the sign-in. With st.login that's this app
# (squareanalysis.streamlit.app) instead of the Supabase project. Streamlit verifies the Google sign-in, exposes
# Google's ID token, and we hand that token to Supabase, which checks it and signs the user in to the database.
# Streamlit doesn't expose the nonce it used, so Supabase's Google provider needs "Skip nonce check" turned on.

def _streamlit_logged_in() -> bool:
    try:
        return bool(st.user.is_logged_in)
    except Exception:  # noqa: BLE001
        return False


def start_streamlit_google() -> None:
    if _streamlit_logged_in():  # a previous Google sign-in didn't reach Supabase; start over cleanly
        st.session_state.pop("_google_bridge_failed", None)
        st.logout()
        return
    st.login("google")


def finish_streamlit_google() -> None:
    """Call at the top of the app: when Streamlit says Google signed someone in, sign them in to Supabase too."""
    if not streamlit_google_configured() or current() is not None or not _streamlit_logged_in():
        return
    if st.session_state.get("_google_bridge_failed"):
        return
    try:
        token = st.user.tokens.get("id")
    except Exception:  # noqa: BLE001
        token = None
    if not token:
        st.session_state._google_bridge_failed = True
        st.session_state.auth_error = ('Google sign-in worked, but no ID token came back. Add expose_tokens = ["id"] '
                                       "under [auth] in the app's secrets.")
        return
    try:
        res = client().auth.sign_in_with_id_token({"provider": "google", "token": token})
        _start_session(res.user)
    except Exception as e:  # noqa: BLE001
        msg = str(getattr(e, "message", "") or e)
        st.session_state._google_bridge_failed = True
        if re.search(r"nonce", msg, re.I):
            st.session_state.auth_error = ("Google sign-in needs one more Supabase setting: turn on Skip nonce check "
                                           "under Authentication → Sign In / Providers → Google.")
        elif re.search(r"audience|aud\b|client.?id", msg, re.I):
            st.session_state.auth_error = ("Supabase doesn't recognise this Google client. Add its client ID under "
                                           "Authentication → Sign In / Providers → Google → Client IDs.")
        elif re.search(r"expired|\bexp\b", msg, re.I):
            st.session_state.auth_error = "Your Google sign-in expired. Please sign in again."
        else:
            st.session_state.auth_error = str(_friendly(e))
