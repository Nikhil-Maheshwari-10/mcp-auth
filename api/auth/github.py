"""
api/auth/github.py — FastAPI route handlers for GitHub OAuth2.

This file is intentionally thin — only HTTP concerns live here:
request parsing, session validation, redirects, and token persistence.

All core OAuth logic (URL building, code exchange) lives in:
    oauth/github/auth.py

Tokens are saved to the CURRENT workspace (from session.active_workspace_id).
"""

import os
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from core.logger import logger
from api.auth.session import get_user_from_session, get_workspace_from_session
from db.token_repo import save_token
from oauth.github.auth import build_auth_url, exchange_code, generate_state

router = APIRouter(prefix="/auth/github", tags=["auth:github"])

_DEFAULT_BASE_URL = os.environ.get("FRONTEND_URL") or (
    f"https://{os.environ.get('NGROK_DOMAIN')}"
    if os.environ.get("NGROK_DOMAIN")
    else "https://trailside-plentiful-humming.ngrok-free.dev"
)

# In-memory state store: {state: {"user_id": str, "workspace_id": str, "_ts": float}}
_pending: dict[str, dict] = {}
_PENDING_TTL = 600  # 10 minutes


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


def _cleanup_stale_pending() -> None:
    now = time.time()
    stale = [k for k, v in list(_pending.items()) if now - v.get("_ts", 0) > _PENDING_TTL]
    for k in stale:
        del _pending[k]


@router.get("/add-account")
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

    workspace_id = await get_workspace_from_session(session_id)

    # ── Enforce MAX_LINKED_GITHUB_ACCOUNTS limit ──────────────────────────
    max_github = int(os.environ.get("MAX_LINKED_GITHUB_ACCOUNTS", "3"))
    from db.token_repo import count_tokens
    current_count = await count_tokens(user_id, "github", workspace_id)
    if current_count >= max_github:
        logger.warning(
            f"GitHub account limit reached for user {user_id} "
            f"(workspace: {workspace_id}): {current_count}/{max_github}"
        )
        return RedirectResponse(
            f"{base_url}/settings?error=github_account_limit_reached&limit={max_github}",
            status_code=303,
        )
    # ─────────────────────────────────────────────────────────────────────

    state = generate_state()
    _pending[state] = {
        "user_id": str(user_id),
        "workspace_id": str(workspace_id) if workspace_id else None,
        "_ts": time.time(),
    }

    redirect_uri = f"{base_url}/api/auth/github/callback"
    logger.info(f"Initiating GitHub OAuth link flow for user {user_id} (workspace: {workspace_id}) (redirect_uri: {redirect_uri})")

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
    _cleanup_stale_pending()

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
    workspace_id_str = pending.get("workspace_id")
    if not user_id_str:
        logger.warning("GitHub OAuth callback missing associated user_id")
        return RedirectResponse(f"{base_url}/login?error=missing_context", status_code=303)

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
        access_token, github_username, provider_account_id, avatar_url = await exchange_code(code, redirect_uri)
    except Exception as exc:
        logger.error(f"GitHub OAuth code exchange failed: {exc}")
        return RedirectResponse(f"{base_url}/settings?error=github_exchange_failed", status_code=303)

    target_ws = uuid.UUID(workspace_id_str) if workspace_id_str else None

    # Resolve the effective user_id — prefer the validated session user,
    # fall back to the one stored in pending state (for cookie-less environments).
    effective_user_id = current_user_id or uuid.UUID(user_id_str)

    # If no workspace is set (single mode), check if a DIFFERENT GitHub token already exists.
    # Only auto-create a workspace when adding a genuinely new/different GitHub account.
    # Re-authing the same account (same provider_account_id) must NOT create a workspace.
    if not target_ws:
        from db.token_repo import get_token
        existing_github = await get_token(effective_user_id, "github", workspace_id=None)
        existing_account_id = existing_github.get("provider_account_id") if existing_github else None
        is_different_account = existing_github and existing_account_id != provider_account_id

        if is_different_account:
            logger.info(
                f"Single-mode user {effective_user_id} adding 2nd GitHub account "
                f"({existing_account_id} → {provider_account_id}) — auto-creating workspace"
            )
            from db.workspace_repo import create_workspace, add_user_to_workspace
            from db.models import User
            from sqlalchemy import select
            from db.connection import AsyncSessionLocal
            from api.auth.session import switch_workspace_in_session

            async with AsyncSessionLocal() as db:
                u_res = await db.execute(select(User).where(User.id == effective_user_id))
                u = u_res.scalar_one_or_none()

            ws_name = f"{(u.email if u else 'My').split('@')[0].replace('.', ' ').title()}'s Workspace"
            target_ws = await create_workspace(ws_name)
            await add_user_to_workspace(target_ws, effective_user_id, role="owner")
            if session_id:
                await switch_workspace_in_session(session_id, target_ws)

            # Copy existing primary GitHub token to the new workspace
            from db.token_repo import save_token as _save_token
            existing_token_data = {
                "access_token": existing_github.get("access_token", ""),
                "provider_username": existing_github.get("provider_username"),
                "provider_account_id": existing_account_id,
                "avatar_url": existing_github.get("avatar_url"),
            }
            await _save_token(effective_user_id, "github", existing_token_data, workspace_id=target_ws)
            logger.info(f"Copied existing GitHub token to new workspace {target_ws}")
        elif existing_github:
            logger.info(
                f"Single-mode user {effective_user_id} re-authenticating existing GitHub account "
                f"({provider_account_id}) — updating token in place, no workspace created"
            )

    await save_token(
        user_id=effective_user_id,
        provider="github",
        token_data={
            "access_token": access_token,
            "provider_username": github_username,
            "provider_account_id": provider_account_id,
            "avatar_url": avatar_url,
        },
        workspace_id=target_ws,
    )

    logger.success(f"GitHub connected successfully for user {effective_user_id} (workspace: {target_ws}) (@{github_username})")
    return RedirectResponse(
        f"{base_url}/settings?github=connected&username={github_username}",
        status_code=303,
    )


@router.delete("/remove-account")
@router.post("/disconnect")
async def github_disconnect(request: Request) -> dict:
    """Unlink and delete GitHub OAuth token from DB for the CURRENT session."""
    from db.token_repo import delete_token
    from core.exceptions import UnauthorizedException
    from core.messages import AUTH_NOT_AUTHENTICATED, AUTH_SESSION_EXPIRED

    session_id = request.cookies.get("session_id")
    if not session_id:
        raise UnauthorizedException(AUTH_NOT_AUTHENTICATED)

    user_id = await get_user_from_session(session_id)
    if not user_id:
        raise UnauthorizedException(AUTH_SESSION_EXPIRED)

    workspace_id = await get_workspace_from_session(session_id)
    provider_account_id = request.query_params.get("provider_account_id", "").strip() or None

    deleted = await delete_token(
        user_id=user_id,
        provider="github",
        provider_account_id=provider_account_id,
        workspace_id=workspace_id,
    )
    return {
        "status": "disconnected" if deleted else "not_found",
        "user_id": str(user_id),
        "workspace_id": str(workspace_id) if workspace_id else None,
    }


@router.post("/set-active")
async def set_active_github_account(request: Request):
    """Set the active GitHub account for the current user/workspace."""
    from db.token_repo import set_active_token

    session_id = request.cookies.get("session_id")
    if not session_id:
        return {"error": "Unauthorized"}, 401

    user_id = await get_user_from_session(session_id)
    if not user_id:
        return {"error": "Session expired"}, 401

    workspace_id = await get_workspace_from_session(session_id)
    provider_account_id = request.query_params.get("provider_account_id", "").strip()

    success = await set_active_token(user_id, "github", provider_account_id, workspace_id)
    return {"status": "success" if success else "failed"}
