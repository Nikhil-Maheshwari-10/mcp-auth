"""
FastAPI application entry point for the workspace auth API.

Routes:
  GET /auth/google/login      — start Google OAuth flow
  GET /auth/google/callback   — Google OAuth callback
  GET /auth/github/login      — start GitHub OAuth flow
  GET /auth/github/callback   — GitHub OAuth callback
  GET /me                     — return current user & active workspace info
  GET /health                 — liveness check
"""

import os
import time
import uuid
from contextlib import asynccontextmanager
import sqlalchemy as sa
from sqlalchemy import select, or_, and_

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.exceptions import AppException, app_exception_handler
from core.logger import logger
from api.auth import google as google_auth
from api.auth import github as github_auth
from api.workspace import router as workspace_router
from api.auth.middleware import get_current_context
from db.engine import AsyncSessionLocal
from db.models import OAuthToken, User, Workspace
from db.workspace_repo import get_workspaces_for_user, get_workspace_by_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log server startup and shutdown."""
    logger.info("Workspace Auth API starting up on port 8001...")
    yield
    logger.info("Workspace Auth API shut down cleanly.")


app = FastAPI(
    title="Workspace Auth API",
    description="Handles OAuth login, session management, and workspaces for the agent.",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — allows the frontend to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.ngrok(-free)?\.(dev|app)|http://localhost(:\d+)?",
    allow_origins=[
        "https://trailside-plentiful-humming.ngrok-free.dev",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:80",
        "http://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming HTTP request with method, path, status, and duration."""
    start_time = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000

    status = response.status_code
    path = request.url.path

    if path == "/health":
        logger.debug(f"{request.method} {path} → {status} ({duration_ms:.1f}ms)")
    elif status >= 400:
        logger.warning(f"{request.method} {path} → {status} ({duration_ms:.1f}ms)")
    else:
        logger.info(f"{request.method} {path} → {status} ({duration_ms:.1f}ms)")

    return response


# Global exception handlers
app.add_exception_handler(AppException, app_exception_handler)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error(f"[API] {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
    else:
        logger.warning(f"[API] {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    detail = "; ".join(f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in errors)
    logger.warning(f"[API] 422 validation error on {request.method} {request.url.path}: {detail}")
    return JSONResponse(status_code=422, content={"error": "Invalid request parameters.", "detail": detail})


app.include_router(google_auth.router)
app.include_router(github_auth.router)
app.include_router(workspace_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.api_route("/auth/logout", methods=["POST"])
async def logout(request: Request, reset_workspace: bool = False) -> JSONResponse:
    """Clear active session from DB and delete authentication cookies.

    If reset_workspace is True:
      - Deletes all OAuth tokens for the active workspace
      - Deletes all ADK chat history (sessions + events) for the workspace
      - Does NOT delete the User record or other workspaces
    """
    from api.auth.session import delete_session, get_user_from_session, get_workspace_from_session
    from db.token_repo import delete_token
    from sqlalchemy import text

    session_id = request.cookies.get("session_id")
    if session_id:
        user_id = await get_user_from_session(session_id)
        workspace_id = await get_workspace_from_session(session_id)

        if reset_workspace and user_id:
            if workspace_id:
                # Workspace mode: delete tokens scoped to this workspace
                await delete_token(user_id, "google", workspace_id=workspace_id)
                await delete_token(user_id, "github", workspace_id=workspace_id)
                logger.info(f"Deleted OAuth tokens for user {user_id} / workspace {workspace_id} on reset logout")
                # ADK chat history: user_id in sessions table = workspace_id string
                adk_uid = str(workspace_id)
            else:
                # Single-account mode: delete tokens with no workspace scope
                await delete_token(user_id, "google", workspace_id=None)
                await delete_token(user_id, "github", workspace_id=None)
                logger.info(f"Deleted OAuth tokens for single-account user {user_id} on reset logout")
                # ADK chat history: user_id in sessions table = user_id string
                adk_uid = str(user_id)

            # Delete ADK chat history — events cascade-deleted by FK ON DELETE CASCADE
            try:
                async with AsyncSessionLocal() as db:
                    async with db.begin():
                        await db.execute(
                            text("DELETE FROM sessions WHERE app_name = 'adk_agent' AND user_id = :uid"),
                            {"uid": adk_uid},
                        )
                logger.info(f"Deleted ADK chat history for adk_uid={adk_uid}")
            except Exception as e:
                logger.error(f"Failed to delete ADK chat history for adk_uid={adk_uid}: {e}")

        await delete_session(session_id)
        logger.info(f"Session '{session_id[:8]}...' cleared")

    res = JSONResponse(content={"status": "logged_out"})
    res.delete_cookie("session_id", path="/", samesite="lax", secure=True)
    res.delete_cookie("google_token_exp", path="/", samesite="lax", secure=True)
    return res


@app.get("/me")
async def me(ctx: tuple[uuid.UUID, uuid.UUID] = Depends(get_current_context)) -> dict:
    """Return the current authenticated user's full profile & active workspace info.

    Protected — requires a valid session_id cookie.
    Returns 401 if the cookie is missing or session expired.
    """
    user_id, workspace_id = ctx
    from core.messages import GOOGLE_SCOPE_GROUPS

    async with AsyncSessionLocal() as db:
        user_result = await db.execute(select(User).where(User.id == user_id))
        user: User | None = user_result.scalar_one_or_none()

        active_ws: Workspace | None = None
        if workspace_id:
            ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
            active_ws = ws_result.scalar_one_or_none()

        if workspace_id:
            tokens_result = await db.execute(
                select(OAuthToken)
                .where(
                    sa.or_(
                        OAuthToken.workspace_id == workspace_id,
                        sa.and_(OAuthToken.user_id == user_id, OAuthToken.workspace_id.is_(None)),
                    )
                )
                .order_by(OAuthToken.workspace_id.is_not(None).desc(), OAuthToken.updated_at.desc())
            )
        else:
            tokens_result = await db.execute(
                select(OAuthToken)
                .where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.workspace_id.is_(None),
                )
                .order_by(OAuthToken.updated_at.desc())
            )
        tokens = tokens_result.scalars().all()

    connected: dict = {}
    google_accounts: list[dict] = []
    github_accounts: list[dict] = []
    ghost_token_ids: list = []
    seen_account_keys: set[str] = set()
    seen_github_account_keys: set[str] = set()

    for token in tokens:
        if token.provider == "google":
            if not token.provider_username or "@" not in token.provider_username:
                logger.warning(
                    f"Removing ghost Google token row (provider_username='{token.provider_username}', "
                    f"account_id='{token.provider_account_id}') for workspace {workspace_id}"
                )
                ghost_token_ids.append(token.provider_account_id)
                continue

            acc_key = token.provider_account_id or token.provider_username
            if acc_key in seen_account_keys:
                continue
            seen_account_keys.add(acc_key)

            granted = set((token.scope or "").split())
            missing = [
                name
                for name, required in GOOGLE_SCOPE_GROUPS.items()
                if not all(s in granted for s in required)
            ]
            avatar = token.avatar_url
            if not avatar and token.provider_account_id:
                async with AsyncSessionLocal() as sub_db:
                    sub_res = await sub_db.execute(
                        select(OAuthToken.avatar_url).where(
                            OAuthToken.user_id == user_id,
                            OAuthToken.provider == token.provider,
                            OAuthToken.avatar_url.is_not(None),
                        ).limit(1)
                    )
                    avatar = sub_res.scalar_one_or_none()

            google_accounts.append({
                "email": token.provider_username,
                "provider_account_id": token.provider_account_id,
                "is_active": token.is_active,
                "scopes": token.scope or "",
                "missing_scopes": missing,
                "connected": True,
                "avatar_url": avatar,
                "is_inherited": token.workspace_id is None,
            })
        elif token.provider == "github":
            acc_key = token.provider_account_id or token.provider_username
            if acc_key in seen_github_account_keys:
                continue
            seen_github_account_keys.add(acc_key)

            github_accounts.append({
                "username": token.provider_username,
                "provider_account_id": token.provider_account_id,
                "is_active": token.is_active,
                "connected": True,
                "avatar_url": token.avatar_url,
                "is_inherited": token.workspace_id is None,
            })

    if ghost_token_ids:
        from db.token_repo import delete_token
        for ghost_id in ghost_token_ids:
            await delete_token(user_id, "google", provider_account_id=ghost_id, workspace_id=workspace_id)

    active_google = next((a for a in google_accounts if a["is_active"]), google_accounts[0] if google_accounts else None)
    if google_accounts:
        connected["google"] = {
            "connected": True,
            "username": active_google["email"] if active_google else None,
            "scopes": active_google["scopes"] if active_google else "",
            "missing_scopes": active_google["missing_scopes"] if active_google else [],
            "accounts": google_accounts,
        }

    active_github = next((a for a in github_accounts if a["is_active"]), github_accounts[0] if github_accounts else None)
    if github_accounts:
        connected["github"] = {
            "connected": True,
            "username": active_github["username"] if active_github else None,
            "accounts": github_accounts,
        }

    email = user.email if user else None
    workspaces = await get_workspaces_for_user(user_id)

    return {
        "user_id": str(user_id),
        "workspace_id": str(workspace_id) if workspace_id else None,
        "workspace_name": active_ws.name if active_ws else None,
        "email": email,
        "connected_providers": connected,
        "workspaces": workspaces,
        "account_limits": {
            "max_gmail_accounts": int(os.environ.get("MAX_LINKED_GMAIL_ACCOUNTS", "3")),
            "max_github_accounts": int(os.environ.get("MAX_LINKED_GITHUB_ACCOUNTS", "3")),
        },
    }
