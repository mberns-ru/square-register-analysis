"""Supabase authentication for the dashboard.

Configure with SUPABASE_URL and SUPABASE_ANON_KEY in .streamlit/secrets.toml (or environment variables).
When they are missing the app runs in local mode without accounts.

Each browser session gets its own Supabase client, so the signed-in user's token is used for every query and
row-level security in the database limits them to their own business.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

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
    (r"error sending (confirmation|recovery|magic link)|email address not authorized|sending email",
     "We couldn't send the email this step needs. The app's email service isn't set up for this address yet. "
     "Please contact the app owner."),
    (r"email rate limit", "Too many emails were sent recently. Please wait an hour and try again."),
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


def sign_out() -> None:
    try:
        client().auth.sign_out()
    except Exception:  # noqa: BLE001
        pass
    for k in ("_sb", "account", "business_id", "auth_mode", "analyst_log"):
        st.session_state.pop(k, None)


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
