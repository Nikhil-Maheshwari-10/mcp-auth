"""
Google OAuth2 auth routes.

GET /auth/google/login    — redirect the browser to Google's consent page
GET /auth/google/callback — receive the code, exchange for tokens, set cookies
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from api.auth.session import create_session
from db.token_repo import upsert_user, save_token
from oauth.common.pkce import generate_code_verifier, generate_code_challenge

load_dotenv()

router = APIRouter(prefix="/auth/google", tags=["auth:google"])

_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
_REDIRECT_URI = os.environ["GOOGLE_API_REDIRECT_URI"]  # e.g. http://localhost:8001/auth/google/callback
_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# In-memory PKCE+state store keyed by state value.
# In production you'd use Redis or a DB — fine for now since this is ephemeral.
_pending: dict[str, dict] = {}


@router.get("/login")
async def google_login() -> RedirectResponse:
    """Redirect the browser to Google's OAuth consent page."""
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)

    _pending[state] = {"code_verifier": code_verifier}

    params = {
        "client_id": _CLIENT_ID,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return RedirectResponse(f"{_AUTH_ENDPOINT}?{urlencode(params)}")


@router.get("/callback")
async def google_callback(request: Request, code: str, state: str) -> RedirectResponse:
    """Receive the OAuth callback, exchange the code, save tokens, set cookies."""
    pending = _pending.pop(state, None)
    if pending is None:
        return RedirectResponse(f"{_FRONTEND_URL}/login?error=invalid_state")

    code_verifier = pending["code_verifier"]

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            _TOKEN_ENDPOINT,
            data={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "redirect_uri": _REDIRECT_URI,
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

        # Fetch user email from Google
        userinfo_resp = await client.get(
            _USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()

    email: str = userinfo["email"]
    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))

    # Upsert user + save token to DB
    user_id = await upsert_user(email)
    await save_token(user_id, "google", {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at,
        "scope": token_data.get("scope", ""),
    })

    # Create browser session
    session_id = await create_session(user_id)

    # Set cookies and redirect to frontend
    response = RedirectResponse(url=_FRONTEND_URL)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,  # 30 days
    )
    response.set_cookie(
        key="google_token_exp",
        value=expires_at.isoformat(),
        httponly=False,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
    return response
