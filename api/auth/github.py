"""
api/auth/github.py — FastAPI route handlers for GitHub OAuth2.

This file is intentionally thin — only HTTP concerns live here:
request parsing, session validation, redirects, and token persistence.

All core OAuth logic (URL building, code exchange) lives in:
    oauth/github/auth.py
"""

import os
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from core.logger import logger
from api.auth.session import get_user_from_session
from db.token_repo import save_token
from oauth.github.auth import build_auth_url, exchange_code, generate_state

router = APIRouter(prefix="/auth/github", tags=["auth:github"])

_DEFAULT_BASE_URL = os.environ.get("FRONTEND_URL") or (
    f"https://{os.environ.get('NGROK_DOMAIN')}"
    if os.environ.get("NGROK_DOMAIN")
    else "https://trailside-plentiful-humming.ngrok-free.dev"
)

# In-memory state store: {state: {"user_id": str}}
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
async def github_login(request: Request) -> RedirectResponse:
    """Start GitHub OAuth connection flow.

    Requires an active Google session (session_id cookie). If not logged in,
    redirects to /login with an error.
    """
    base_url = _get_base_url(request)
    session_id = request.cookies.get("session_id")

    if not session_id:
        logger.warning("GitHub connect attempt rejected: user not logged in with Google")
        return RedirectResponse(f"{base_url}/login?error=login_with_google_first")

    user_id = await get_user_from_session(session_id)
    if not user_id:
        logger.warning("GitHub connect attempt rejected: session expired")
        return RedirectResponse(f"{base_url}/login?error=session_expired")

    state = generate_state()
    _pending[state] = {"user_id": str(user_id)}

    redirect_uri = f"{base_url}/api/auth/github/callback"
    logger.info(f"Initiating GitHub OAuth link flow for user {user_id} (redirect_uri: {redirect_uri})")

    return RedirectResponse(build_auth_url(redirect_uri, state))


@router.get("/callback")
async def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    """Receive the GitHub OAuth callback."""
    base_url = _get_base_url(request)
    session_id = request.cookies.get("session_id")

    if error or not code:
        logger.warning(f"GitHub OAuth cancelled or denied: error='{error}', desc='{error_description}'")
        if session_id and await get_user_from_session(session_id):
            return RedirectResponse(f"{base_url}/settings?github=cancelled", status_code=303)
        return RedirectResponse(f"{base_url}/login?error=github_cancelled", status_code=303)

    pending = _pending.pop(state, None) if state else None
    if pending is None:
        logger.warning(f"GitHub OAuth callback rejected: state '{state}' not found")
        if session_id and await get_user_from_session(session_id):
            return RedirectResponse(f"{base_url}/settings", status_code=303)
        return RedirectResponse(f"{base_url}/settings?error=invalid_state", status_code=303)

    user_id_str = pending.get("user_id")
    if not user_id_str:
        logger.warning("GitHub OAuth callback missing associated user_id")
        return RedirectResponse(f"{base_url}/login?error=missing_user", status_code=303)

    # Verify active session matches the user who initiated GitHub link
    current_user_id = await get_user_from_session(session_id) if session_id else None
    if current_user_id and str(current_user_id) != user_id_str:
        logger.warning(
            f"GitHub OAuth callback rejected: active user ({current_user_id}) does not match "
            f"initiating user ({user_id_str}). Account switch may have occurred."
        )
        return RedirectResponse(f"{base_url}/settings?error=user_mismatch", status_code=303)

    redirect_uri = f"{base_url}/api/auth/github/callback"
    logger.info(f"Exchanging GitHub authorization code for tokens (redirect_uri: {redirect_uri})")

    try:
        access_token, github_username = await exchange_code(code, redirect_uri)
    except Exception as exc:
        logger.error(f"GitHub OAuth code exchange failed: {exc}")
        return RedirectResponse(f"{base_url}/settings?error=github_exchange_failed", status_code=303)

    user_id = uuid.UUID(user_id_str)
    await save_token(user_id, "github", {
        "access_token": access_token,
        "provider_username": github_username,
    })

    logger.success(f"GitHub connected successfully for user {user_id} (@{github_username})")
    return RedirectResponse(
        f"{base_url}/settings?github=connected&username={github_username}",
        status_code=303,
    )


@router.post("/disconnect")
async def github_disconnect(request: Request) -> dict:
    """Unlink and delete GitHub OAuth token from DB for current session user."""
    from db.token_repo import delete_token
    from core.exceptions import UnauthorizedException
    from core.messages import AUTH_NOT_AUTHENTICATED, AUTH_SESSION_EXPIRED

    session_id = request.cookies.get("session_id")
    if not session_id:
        raise UnauthorizedException(AUTH_NOT_AUTHENTICATED)

    user_id = await get_user_from_session(session_id)
    if not user_id:
        raise UnauthorizedException(AUTH_SESSION_EXPIRED)

    deleted = await delete_token(user_id, "github")
    return {"status": "disconnected" if deleted else "not_found", "user_id": str(user_id)}
