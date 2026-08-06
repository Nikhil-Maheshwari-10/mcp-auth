"""
oauth/google/auth.py — Core Google OAuth2 logic.

Pure functions — no FastAPI, no HTTP request objects.
Called by api/auth/google.py (FastAPI routes) and usable in tests independently.

Public API:
    SCOPES                 — list of OAuth scopes requested
    build_auth_url(...)    — constructs the Google authorization URL
    exchange_code(...)     — exchanges an auth code for tokens + userinfo
    detect_missing_scopes(granted_scope_str) → list[str]
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv

from core.logger import logger
from core.messages import GOOGLE_SCOPE_GROUPS
from oauth.common.pkce import generate_code_verifier, generate_code_challenge

load_dotenv()

# ── OAuth Endpoints ────────────────────────────────────────────────────────────

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# ── OAuth Scopes ───────────────────────────────────────────────────────────────

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

# ── Credentials (read once at import time) ─────────────────────────────────────

CLIENT_ID: str = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET: str = os.environ["GOOGLE_CLIENT_SECRET"]


# ── Core Functions ─────────────────────────────────────────────────────────────

def detect_missing_scopes(granted_scope_str: str) -> list[str]:
    """Return scope category names that were NOT granted by the user.

    Args:
        granted_scope_str: Space-separated scope string returned by Google token endpoint.

    Returns:
        List of category names (e.g. ['gmail', 'calendar']) whose required scopes
        are absent from the granted set. Empty list means full consent was given.
    """
    granted = set(granted_scope_str.split())
    return [
        name
        for name, required in GOOGLE_SCOPE_GROUPS.items()
        if not all(s in granted for s in required)
    ]


def build_auth_url(
    redirect_uri: str,
    code_challenge: str,
    state: str,
    login_hint: str | None = None,
) -> str:
    """Build the Google OAuth2 authorization URL.

    Args:
        redirect_uri:    Where Google should send the user after consent.
        code_challenge:  PKCE code challenge (S256).
        state:           Opaque CSRF state token.
        login_hint:      Pre-fill the Google account picker with this email.

    Returns:
        Full authorization URL to redirect the browser to.
    """
    params: dict[str, str] = {
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


def generate_pkce_state() -> tuple[str, str, str]:
    """Generate a fresh PKCE verifier, challenge, and state token.

    Returns:
        (code_verifier, code_challenge, state)
    """
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)
    return code_verifier, code_challenge, state


async def exchange_code(
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> tuple[dict, dict]:
    """Exchange an authorization code for tokens and userinfo.

    Args:
        code:          The authorization code received from Google's callback.
        code_verifier: The PKCE verifier that matches the challenge sent in the auth URL.
        redirect_uri:  Must exactly match the redirect_uri used in the auth URL.

    Returns:
        (token_data, userinfo) — both dicts from Google APIs.
        token_data keys: access_token, refresh_token (maybe), expires_in, scope, ...
        userinfo keys: email, name, sub, picture, ...

    Raises:
        httpx.HTTPStatusError: On non-2xx response from Google.
        Exception: On network or unexpected error.
    """
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            TOKEN_ENDPOINT,
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

        userinfo_resp = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()

    logger.debug(f"[GOOGLE AUTH] Token exchange successful for '{userinfo.get('email')}'")
    return token_data, userinfo


def token_expires_at(token_data: dict) -> datetime:
    """Compute the token expiry datetime from a token_data dict."""
    return datetime.now(tz=timezone.utc) + timedelta(
        seconds=token_data.get("expires_in", 3600)
    )
