"""
api/auth/google.py — FastAPI route handlers for Google OAuth2.

This file is intentionally thin — only HTTP concerns live here:
request parsing, cookie management, redirects, and session creation.

All core OAuth logic (URL building, code exchange, scope detection) lives in:
    oauth/google/auth.py
"""

import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from core.logger import logger
from api.auth.session import create_session, get_user_from_session
from db.token_repo import upsert_user, save_token
from oauth.google.auth import (
    build_auth_url,
    exchange_code,
    detect_missing_scopes,
    generate_pkce_state,
    token_expires_at,
)

router = APIRouter(prefix="/auth/google", tags=["auth:google"])

_DEFAULT_BASE_URL = os.environ.get("FRONTEND_URL") or (
    f"https://{os.environ.get('NGROK_DOMAIN')}"
    if os.environ.get("NGROK_DOMAIN")
    else "https://trailside-plentiful-humming.ngrok-free.dev"
)

# In-memory PKCE+state store keyed by state value.
# Each entry: {"code_verifier": str, "reauth": bool, "email": str | None}
_pending: dict[str, dict] = {}


def _get_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if (
        host
        and "api:" not in host
        and "adk:" not in host
        and not host.startswith("127.")
        and not host.startswith("172.")
        and not host.startswith("192.")
        and "localhost" not in host
    ):
        return f"{proto}://{host}"
    return _DEFAULT_BASE_URL


@router.get("/login")
async def google_login(request: Request) -> RedirectResponse:
    """Redirect the browser to Google's OAuth consent page (initial login)."""
    code_verifier, code_challenge, state = generate_pkce_state()
    _pending[state] = {"code_verifier": code_verifier, "reauth": False, "email": None}

    base_url = _get_base_url(request)
    redirect_uri = f"{base_url}/api/auth/google/callback"
    logger.info(f"Initiating Google OAuth login flow (redirect_uri: {redirect_uri})")

    return RedirectResponse(build_auth_url(redirect_uri, code_challenge, state))


@router.get("/reauth")
async def google_reauth(request: Request) -> RedirectResponse:
    """Re-authorize to grant missing scopes (e.g. Calendar write access).

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

    code_verifier, code_challenge, state = generate_pkce_state()
    _pending[state] = {"code_verifier": code_verifier, "reauth": True, "email": email}

    redirect_uri = f"{base_url}/api/auth/google/callback"
    logger.info(f"Initiating Google re-authorization for '{email}' (redirect_uri: {redirect_uri})")

    return RedirectResponse(build_auth_url(redirect_uri, code_challenge, state, login_hint=email))


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
        logger.warning(f"Google OAuth cancelled or denied: error='{error}', desc='{error_description}'")
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

    redirect_uri = f"{base_url}/api/auth/google/callback"
    logger.info(f"Exchanging Google authorization code for tokens (reauth={is_reauth})")

    try:
        token_data, userinfo = await exchange_code(code, pending["code_verifier"], redirect_uri)
    except Exception as exc:
        logger.error(f"Google OAuth code exchange failed: {exc}")
        dest = "/settings?error=token_exchange_failed" if is_reauth else "/login?error=token_exchange_failed"
        return RedirectResponse(f"{frontend_url}{dest}", status_code=303)

    email: str = userinfo["email"]
    granted_scope = token_data.get("scope", "")
    expires_at = token_expires_at(token_data)

    # Detect partial consent
    missing_scopes = detect_missing_scopes(granted_scope)
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
        logger.success(f"Google re-authorization successful for '{email}' (user_id: {user_id})")
        qs = f"?reauth=success&missing_scopes={','.join(missing_scopes)}" if missing_scopes else "?reauth=success"
        return RedirectResponse(url=f"{frontend_url}/settings{qs}", status_code=303)

    # Normal login: create session and set cookies
    logger.success(f"Google authentication successful for user '{email}' (user_id: {user_id})")
    session_id = await create_session(user_id)

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
