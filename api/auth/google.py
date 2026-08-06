"""
Google OAuth2 auth routes.

GET /auth/google/login    — redirect to Google's consent page (initial login)
GET /auth/google/reauth  — re-authorize to add missing scopes (e.g. Calendar)
GET /auth/google/callback — receive OAuth code, exchange tokens, set cookies
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from core.logger import logger
from core.messages import GOOGLE_SCOPE_GROUPS
from api.auth.session import create_session, get_user_from_session
from db.token_repo import upsert_user, save_token
from oauth.common.pkce import generate_code_verifier, generate_code_challenge

load_dotenv()

router = APIRouter(prefix="/auth/google", tags=["auth:google"])

_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
_DEFAULT_BASE_URL = os.environ.get("FRONTEND_URL") or (
    f"https://{os.environ.get('NGROK_DOMAIN')}" if os.environ.get("NGROK_DOMAIN") else "https://trailside-plentiful-humming.ngrok-free.dev"
)

_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

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

# In-memory PKCE+state store keyed by state value.
# Each entry: {"code_verifier": str, "reauth": bool, "email": str | None}
_pending: dict[str, dict] = {}


def _get_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host and "api:" not in host and "adk:" not in host and not host.startswith("127.") and not host.startswith("172.") and not host.startswith("192.") and "localhost" not in host:
        return f"{proto}://{host}"
    return _DEFAULT_BASE_URL


def _detect_missing_scopes(granted_scope_str: str) -> list[str]:
    """Return a list of scope category names (e.g. ['calendar']) that were NOT granted."""
    granted = set(granted_scope_str.split())
    missing = [
        name
        for name, required in GOOGLE_SCOPE_GROUPS.items()
        if not all(s in granted for s in required)
    ]
    return missing


def _build_auth_url(
    redirect_uri: str,
    code_challenge: str,
    state: str,
    login_hint: str | None = None,
) -> str:
    """Build a Google OAuth authorization URL."""
    params: dict[str, str] = {
        "client_id": _CLIENT_ID,
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
    return f"{_AUTH_ENDPOINT}?{urlencode(params)}"


@router.get("/login")
async def google_login(request: Request) -> RedirectResponse:
    """Redirect the browser to Google's OAuth consent page (initial login)."""
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)

    _pending[state] = {"code_verifier": code_verifier, "reauth": False, "email": None}

    base_url = _get_base_url(request)
    redirect_uri = f"{base_url}/api/auth/google/callback"
    logger.info(f"Initiating Google OAuth login flow (redirect_uri: {redirect_uri})")

    return RedirectResponse(_build_auth_url(redirect_uri, code_challenge, state))


@router.get("/reauth")
async def google_reauth(request: Request) -> RedirectResponse:
    """Re-authorize to grant missing scopes (e.g. Calendar).

    Requires an active session. Passes login_hint=<email> so Google skips the
    account picker. On callback, updates the existing token row (no new user/session).
    """
    session_id = request.cookies.get("session_id")
    base_url = _get_base_url(request)

    if not session_id:
        logger.warning("Reauth attempted without active session — redirecting to login")
        return RedirectResponse(f"{base_url}/login", status_code=303)

    user_id = await get_user_from_session(session_id)
    if user_id is None:
        logger.warning("Reauth: session not found in DB")
        return RedirectResponse(f"{base_url}/login?error=session_expired", status_code=303)

    # Look up the user's email to provide login_hint
    from db.engine import AsyncSessionLocal
    from db.models import User
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    email = user.email if user else None

    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)

    _pending[state] = {"code_verifier": code_verifier, "reauth": True, "email": email}

    redirect_uri = f"{base_url}/api/auth/google/callback"
    logger.info(f"Initiating Google re-authorization for '{email}' (redirect_uri: {redirect_uri})")

    return RedirectResponse(_build_auth_url(redirect_uri, code_challenge, state, login_hint=email))


@router.get("/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    """Receive the OAuth callback, exchange the code, save tokens, set cookies."""
    base_url = _get_base_url(request)
    frontend_url = base_url

    if error or not code:
        logger.warning(f"Google OAuth cancelled or denied by user: error='{error}', desc='{error_description}'")
        session_id = request.cookies.get("session_id")
        if session_id and await get_user_from_session(session_id):
            return RedirectResponse(f"{base_url}/settings?google=cancelled", status_code=303)
        return RedirectResponse(f"{base_url}/login?error=google_cancelled", status_code=303)

    pending = _pending.pop(state, None) if state else None
    is_reauth = pending.get("reauth", False) if pending else False

    # For normal login: if session already exists, go home (prevents replay issues)
    if not is_reauth:
        existing_session = request.cookies.get("session_id")
        if existing_session and await get_user_from_session(existing_session):
            logger.info("Active session already present during OAuth callback — redirecting to home")
            return RedirectResponse(url=f"{frontend_url}/", status_code=303)

    if pending is None:
        logger.warning(f"Google OAuth callback rejected: state '{state}' not found in pending requests")
        return RedirectResponse(f"{base_url}/login?error=invalid_state", status_code=303)

    code_verifier = pending["code_verifier"]
    redirect_uri = f"{base_url}/api/auth/google/callback"

    logger.info(f"Exchanging Google authorization code for tokens (reauth={is_reauth})")

    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                _TOKEN_ENDPOINT,
                data={
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                },
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()

            userinfo_resp = await client.get(
                _USERINFO_URL,
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()
    except Exception as exc:
        logger.error(f"Google OAuth code exchange failed: {exc}")
        dest = "/settings?error=token_exchange_failed" if is_reauth else "/login?error=token_exchange_failed"
        return RedirectResponse(f"{frontend_url}{dest}", status_code=303)

    email: str = userinfo["email"]
    granted_scope = token_data.get("scope", "")
    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))

    # ── Detect partial consent ──────────────────────────────────────────────
    missing_scopes = _detect_missing_scopes(granted_scope)
    if missing_scopes:
        logger.warning(
            f"Partial consent detected for '{email}': missing scope groups = {missing_scopes}. "
            "Token saved but some tools will be unavailable."
        )
    else:
        logger.success(f"Full consent granted for '{email}' — all scope groups present")

    # Upsert user + save token
    user_id = await upsert_user(email)
    await save_token(user_id, "google", {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at,
        "scope": granted_scope,
        "provider_username": userinfo.get("name") or email,
    })

    is_https = base_url.startswith("https://")

    if is_reauth:
        # Re-auth: update token, redirect back to Settings (keep existing session cookie)
        logger.success(f"Google re-authorization successful for '{email}' (user_id: {user_id})")
        if missing_scopes:
            qs = f"?reauth=success&missing_scopes={','.join(missing_scopes)}"
        else:
            qs = "?reauth=success"
        return RedirectResponse(url=f"{frontend_url}/settings{qs}", status_code=303)

    # Normal login: create session and set cookies
    logger.success(f"Google authentication successful for user '{email}' (user_id: {user_id})")
    session_id = await create_session(user_id)

    # Build redirect with scope info so frontend can show warnings immediately
    qs = f"?missing_scopes={','.join(missing_scopes)}" if missing_scopes else ""
    response = RedirectResponse(url=f"{frontend_url}/{qs}", status_code=303)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=is_https,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
    response.set_cookie(
        key="google_token_exp",
        value=expires_at.isoformat(),
        httponly=False,
        secure=is_https,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
    return response

