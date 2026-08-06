"""
GitHub OAuth2 auth routes.

GET /auth/github/login    — redirect the browser to GitHub's authorization page
GET /auth/github/callback — receive the code, exchange for token, store under
                            existing Google session user_id (GitHub is a connection,
                            NOT a login provider — Google is the primary identity)

IMPORTANT: GitHub callback requires an active session_id cookie (i.e., user must
be logged in with Google first). This prevents GitHub from creating a separate
User row with a different email, which would break token isolation.
"""

import os
import secrets
import uuid
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from core.logger import logger
from api.auth.session import get_user_from_session
from db.token_repo import save_token

load_dotenv()

router = APIRouter(prefix="/auth/github", tags=["auth:github"])

_CLIENT_ID = os.environ["GITHUB_CLIENT_ID"]
_CLIENT_SECRET = os.environ["GITHUB_CLIENT_SECRET"]
_DEFAULT_BASE_URL = os.environ.get("FRONTEND_URL") or (
    f"https://{os.environ.get('NGROK_DOMAIN')}" if os.environ.get("NGROK_DOMAIN") else "https://trailside-plentiful-humming.ngrok-free.dev"
)

_AUTH_ENDPOINT = "https://github.com/login/oauth/authorize"
_TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"
_USER_URL = "https://api.github.com/user"
_EMAILS_URL = "https://api.github.com/user/emails"

SCOPES = ["read:user", "user:email", "repo", "notifications"]

_pending: dict[str, dict] = {}


def _get_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host and "api:" not in host and "adk:" not in host and not host.startswith("127.") and not host.startswith("172.") and not host.startswith("192.") and "localhost" not in host:
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

    state = secrets.token_urlsafe(16)
    _pending[state] = {"user_id": str(user_id)}

    redirect_uri = f"{base_url}/api/auth/github/callback"

    logger.info(f"Initiating GitHub OAuth link flow for user {user_id} (redirect_uri: {redirect_uri})")

    params = {
        "client_id": _CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
    }
    return RedirectResponse(f"{_AUTH_ENDPOINT}?{urlencode(params)}")


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
    frontend_url = base_url
    session_id = request.cookies.get("session_id")

    if error or not code:
        logger.warning(f"GitHub OAuth cancelled or denied by user: error='{error}', desc='{error_description}'")
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
    redirect_uri = f"{base_url}/api/auth/github/callback"

    if not user_id_str:
        logger.warning("GitHub OAuth callback missing associated user_id")
        return RedirectResponse(f"{frontend_url}/login?error=missing_user", status_code=303)

    # Verify active session matches the user who initiated GitHub link
    current_user_id = await get_user_from_session(session_id) if session_id else None
    if current_user_id and str(current_user_id) != user_id_str:
        logger.warning(
            f"GitHub OAuth callback rejected: active user ({current_user_id}) does not match "
            f"initiating user ({user_id_str}). Account switch may have occurred."
        )
        return RedirectResponse(f"{frontend_url}/settings?error=user_mismatch", status_code=303)

    logger.info(f"Exchanging GitHub authorization code for tokens (redirect_uri: {redirect_uri})")

    # Exchange code for GitHub access token
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                _TOKEN_ENDPOINT,
                data={
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()

            if "error" in token_data:
                logger.error(f"GitHub token exchange error: {token_data.get('error_description')}")
                return RedirectResponse(f"{frontend_url}/settings?error=github_exchange_failed", status_code=303)

            access_token = token_data["access_token"]

            # Fetch GitHub username
            user_resp = await client.get(
                _USER_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_resp.raise_for_status()
            user_info = user_resp.json()
            github_username = user_info.get("login", "")

    except Exception as exc:
        logger.error(f"GitHub OAuth code exchange failed: {exc}")
        return RedirectResponse(f"{frontend_url}/settings?error=github_exchange_failed", status_code=303)

    user_id = uuid.UUID(user_id_str)

    # Save token — upserts GitHub row without touching User table
    await save_token(user_id, "github", {
        "access_token": access_token,
        "scope": token_data.get("scope", ""),
        "provider_username": github_username,
    })

    logger.success(f"GitHub connected successfully for user {user_id} (@{github_username})")
    return RedirectResponse(f"{frontend_url}/settings?github=connected&username={github_username}", status_code=303)


@router.post("/disconnect")
async def github_disconnect(request: Request) -> dict:
    """Unlink and delete GitHub OAuth token from DB for current session user."""
    from api.auth.middleware import get_current_user
    from db.token_repo import delete_token
    from fastapi import Depends

    session_id = request.cookies.get("session_id")
    if not session_id:
        from core.exceptions import UnauthorizedException
        from core.messages import AUTH_NOT_AUTHENTICATED
        raise UnauthorizedException(AUTH_NOT_AUTHENTICATED)

    user_id = await get_user_from_session(session_id)
    if not user_id:
        from core.exceptions import UnauthorizedException
        from core.messages import AUTH_SESSION_EXPIRED
        raise UnauthorizedException(AUTH_SESSION_EXPIRED)

    deleted = await delete_token(user_id, "github")
    return {"status": "disconnected" if deleted else "not_found", "user_id": str(user_id)}

