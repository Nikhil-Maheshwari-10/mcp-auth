"""
api/auth/google.py — FastAPI route handlers for Google OAuth2.
"""

import os
import time
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from core.logger import logger
from api.auth.session import create_session, get_user_from_session, get_workspace_from_session
from db.token_repo import (
    save_token,
    get_token,
    get_all_provider_tokens,
    upsert_user_by_sub,
    delete_token,
    set_active_token,
)
from db.workspace_repo import (
    get_workspace_id_by_provider_sub,
    get_workspaces_for_user,
)
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

_pending: dict[str, dict] = {}
_PENDING_TTL = 600


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


@router.get("/login")
async def google_login(request: Request) -> RedirectResponse:
    """Redirect to Google consent page."""
    code_verifier, code_challenge, state = generate_pkce_state()
    _pending[state] = {"code_verifier": code_verifier, "reauth": False, "email": None, "_ts": time.time()}

    base_url = _get_base_url(request)
    redirect_uri = f"{base_url}/api/auth/google/callback"
    return RedirectResponse(build_auth_url(redirect_uri, code_challenge, state))


@router.get("/reauth")
async def google_reauth(request: Request) -> RedirectResponse:
    session_id = request.cookies.get("session_id")
    base_url = _get_base_url(request)

    if not session_id:
        return RedirectResponse(f"{base_url}/login", status_code=303)

    user_id = await get_user_from_session(session_id)
    if user_id is None:
        return RedirectResponse(f"{base_url}/login?error=session_expired", status_code=303)

    # Use the explicitly requested account_email if provided by the frontend.
    # Falls back to the session owner's primary email for single-account mode.
    account_email = request.query_params.get("account_email", "").strip()
    if not account_email:
        from db.engine import AsyncSessionLocal
        from db.models import User
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
        account_email = user.email if user else None

    code_verifier, code_challenge, state = generate_pkce_state()
    _pending[state] = {
        "code_verifier": code_verifier,
        "reauth": True,
        "email": account_email,  # target account — validated in callback
        "_ts": time.time(),
    }

    redirect_uri = f"{base_url}/api/auth/google/callback"
    return RedirectResponse(build_auth_url(redirect_uri, code_challenge, state, login_hint=account_email))


@router.get("/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    _cleanup_stale_pending()

    base_url = _get_base_url(request)
    frontend_url = base_url

    if error or not code:
        session_id = request.cookies.get("session_id")
        if session_id and await get_user_from_session(session_id):
            return RedirectResponse(f"{base_url}/settings?google=cancelled", status_code=303)
        return RedirectResponse(f"{base_url}/login?error=google_cancelled", status_code=303)

    pending = _pending.pop(state, None) if state else None
    if pending is None:
        return RedirectResponse(f"{base_url}/login?error=invalid_state", status_code=303)

    is_reauth = pending.get("reauth", False)
    is_add_account = pending.get("add_account", False)

    existing_session = request.cookies.get("session_id")
    existing_user_id = await get_user_from_session(existing_session) if existing_session else None
    existing_workspace_id = await get_workspace_from_session(existing_session) if existing_session else None

    if not is_reauth and not is_add_account and existing_user_id:
        return RedirectResponse(url=f"{frontend_url}/", status_code=303)

    redirect_uri = f"{base_url}/api/auth/google/callback"
    try:
        token_data, userinfo = await exchange_code(code, pending["code_verifier"], redirect_uri)
    except Exception as exc:
        dest = "/settings?error=token_exchange_failed" if (is_reauth or is_add_account) else "/login?error=token_exchange_failed"
        return RedirectResponse(f"{frontend_url}{dest}", status_code=303)

    email: str = userinfo["email"]
    sub: str = userinfo.get("sub") or userinfo.get("id") or email
    granted_scope = token_data.get("scope", "")
    expires_at = token_expires_at(token_data)

    missing_scopes = detect_missing_scopes(granted_scope)

    # Validate the returned account matches the intended reauth target
    intended_email = pending.get("email")
    if is_reauth and intended_email and email.lower() != intended_email.lower():
        logger.warning(
            f"Reauth account mismatch: intended='{intended_email}', got='{email}'. "
            "Token will be saved to the returned account's row (safe — keyed by sub)."
        )

    # ─── Identity resolution ──────────────────────────────────────────────────
    if existing_user_id:
        user_id = existing_user_id
        workspace_id = existing_workspace_id

        # Adding a 2nd account strictly requires a workspace.
        # Only auto-create a workspace when explicitly adding a new account (not on re-auth).
        if is_add_account and not workspace_id:
            from db.models import User
            from db.engine import AsyncSessionLocal
            from db.workspace_repo import create_workspace, add_user_to_workspace
            from api.auth.session import switch_workspace_in_session
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                u_res = await db.execute(select(User).where(User.id == user_id))
                u = u_res.scalar_one_or_none()

            ws_name = f"{(u.email if u else 'My').split('@')[0].replace('.', ' ').title()}'s Workspace"
            workspace_id = await create_workspace(ws_name)
            await add_user_to_workspace(workspace_id, user_id, role="owner")
            if existing_session:
                await switch_workspace_in_session(existing_session, workspace_id)

            # Copy existing primary login token to the new workspace
            primary_token = await get_token(user_id, "google", workspace_id=None)
            if primary_token:
                await save_token(user_id, "google", primary_token, workspace_id=workspace_id)
    else:
        user_id = await upsert_user_by_sub(sub, email)
        workspace_id = None  # Standard single account login — no workspace auto-creation!

    await save_token(
        user_id=user_id,
        provider="google",
        token_data={
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": expires_at,
            "scope": granted_scope,
            "provider_username": email,
            "provider_account_id": sub,
            "avatar_url": userinfo.get("picture"),
        },
        workspace_id=workspace_id,
    )

    is_https = base_url.startswith("https://")

    if is_reauth or is_add_account or existing_user_id:
        qs = f"?account_added=success&email={email}"
        if missing_scopes:
            qs += f"&missing_scopes={','.join(missing_scopes)}"
        return RedirectResponse(url=f"{frontend_url}/settings{qs}", status_code=303)

    # Fresh login — create session without forced workspace
    session_id = await create_session(user_id, workspace_id=None)
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


@router.get("/add-account")
async def google_add_account(request: Request) -> RedirectResponse:
    """Start OAuth to add a 2nd Google account.

    The frontend must have already created a workspace (via POST /workspace/create)
    before calling this endpoint, so the session already carries a workspace_id.
    This route only enforces the account limit and starts the OAuth flow.
    """
    session_id = request.cookies.get("session_id")
    base_url = _get_base_url(request)

    if not session_id:
        return RedirectResponse(f"{base_url}/login", status_code=303)

    user_id = await get_user_from_session(session_id)
    if user_id is None:
        return RedirectResponse(f"{base_url}/login?error=session_expired", status_code=303)

    workspace_id = await get_workspace_from_session(session_id)

    # ── Enforce MAX_LINKED_GMAIL_ACCOUNTS limit ───────────────────────────
    max_gmail = int(os.environ.get("MAX_LINKED_GMAIL_ACCOUNTS", "3"))
    from db.token_repo import count_tokens
    current_count = await count_tokens(user_id, "google", workspace_id)
    if current_count >= max_gmail:
        logger.warning(
            f"Gmail account limit reached for user {user_id} "
            f"(workspace: {workspace_id}): {current_count}/{max_gmail}"
        )
        return RedirectResponse(
            f"{base_url}/settings?error=gmail_account_limit_reached&limit={max_gmail}",
            status_code=303,
        )
    # ─────────────────────────────────────────────────────────────────────

    # workspace_id is expected to be set by the frontend via POST /workspace/create
    # before reaching here. If somehow still None, log a warning but proceed —
    # the callback will save the new token to the null-workspace scope (single mode).
    if not workspace_id:
        logger.warning(
            f"User {user_id} reached /add-account without an active workspace — "
            "frontend should have created one first. Proceeding in single mode."
        )

    code_verifier, code_challenge, state = generate_pkce_state()
    _pending[state] = {"code_verifier": code_verifier, "reauth": False, "email": None, "add_account": True, "_ts": time.time()}

    redirect_uri = f"{base_url}/api/auth/google/callback"
    logger.info(f"Initiating add-account OAuth for user {user_id} (workspace: {workspace_id})")
    return RedirectResponse(build_auth_url(redirect_uri, code_challenge, state))


@router.delete("/remove-account")
async def google_remove_account(request: Request) -> JSONResponse:
    session_id = request.cookies.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    user_id = await get_user_from_session(session_id)
    if not user_id:
        return JSONResponse({"error": "Session expired"}, status_code=401)

    workspace_id = await get_workspace_from_session(session_id)
    provider_account_id = request.query_params.get("provider_account_id", "").strip()
    if not provider_account_id:
        return JSONResponse({"error": "provider_account_id is required"}, status_code=400)

    deleted = await delete_token(user_id, "google", provider_account_id, workspace_id)
    return JSONResponse({"status": "removed" if deleted else "not_found"})


@router.post("/set-active")
async def set_active_account(request: Request) -> JSONResponse:
    session_id = request.cookies.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    user_id = await get_user_from_session(session_id)
    if not user_id:
        return JSONResponse({"error": "Session expired"}, status_code=401)

    workspace_id = await get_workspace_from_session(session_id)
    provider_account_id = request.query_params.get("provider_account_id", "").strip()

    success = await set_active_token(user_id, "google", provider_account_id, workspace_id)
    return JSONResponse({"status": "success" if success else "failed"})
