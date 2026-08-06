"""
FastAPI application entry point for the workspace auth API.

Routes:
  GET /auth/google/login      — start Google OAuth flow
  GET /auth/google/callback   — Google OAuth callback
  GET /auth/github/login      — start GitHub OAuth flow
  GET /auth/github/callback   — GitHub OAuth callback
  GET /me                     — return current user info (requires session cookie)
  GET /health                 — liveness check

Run locally:
    uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
"""

import time
import uuid
from contextlib import asynccontextmanager
from sqlalchemy import select

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.exceptions import AppException, app_exception_handler

from core.logger import logger
from api.auth import google as google_auth
from api.auth import github as github_auth
from api.auth.middleware import get_current_user
from db.engine import AsyncSessionLocal
from db.models import OAuthToken, User


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log server startup and shutdown."""
    logger.info("Workspace Auth API starting up on port 8001...")
    yield
    logger.info("Workspace Auth API shut down cleanly.")


app = FastAPI(
    title="Workspace Auth API",
    description="Handles OAuth login and session management for the workspace agent.",
    version="0.1.0",
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

    # Keep health checks unobtrusive
    if path == "/health":
        logger.debug(f"{request.method} {path} → {status} ({duration_ms:.1f}ms)")
    elif status >= 400:
        logger.warning(f"{request.method} {path} → {status} ({duration_ms:.1f}ms)")
    else:
        logger.info(f"{request.method} {path} → {status} ({duration_ms:.1f}ms)")

    return response


# ── Global exception handlers ────────────────────────────────────────────
# Uniform JSON shape: {"error": "<message>"} for all structured app errors
app.add_exception_handler(AppException, app_exception_handler)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Catch plain FastAPI HTTPExceptions and return consistent {error: ...} JSON."""
    from core.logger import logger
    if exc.status_code >= 500:
        logger.error(f"[API] {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
    else:
        logger.warning(f"[API] {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Catch Pydantic validation errors and return a clean 422 response."""
    from core.logger import logger
    errors = exc.errors()
    detail = "; ".join(f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in errors)
    logger.warning(f"[API] 422 validation error on {request.method} {request.url.path}: {detail}")
    return JSONResponse(status_code=422, content={"error": "Invalid request parameters.", "detail": detail})


app.include_router(google_auth.router)
app.include_router(github_auth.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.api_route("/auth/logout", methods=["GET", "POST"])
async def logout(request: Request) -> JSONResponse:
    """Clear active session from DB and delete authentication cookies."""
    from api.auth.session import delete_session

    session_id = request.cookies.get("session_id")
    if session_id:
        await delete_session(session_id)
        logger.info(f"User logged out, session '{session_id[:8]}...' cleared")

    res = JSONResponse(content={"status": "logged_out"})
    res.delete_cookie("session_id", path="/")
    res.delete_cookie("google_token_exp", path="/")
    return res


@app.get("/me")
async def me(user_id: uuid.UUID = Depends(get_current_user)) -> dict:
    """Return the current authenticated user's full profile.

    Used by the frontend Settings and Chat pages to display:
      - Google email (primary identity)
      - GitHub username (if connected)
      - Which providers are linked
      - Which Google scope groups are missing (for consent gap detection)

    Protected — requires a valid session_id cookie.
    Returns 401 if the cookie is missing or the session has expired.
    """
    from core.messages import GOOGLE_SCOPE_GROUPS

    async with AsyncSessionLocal() as db:
        user_result = await db.execute(select(User).where(User.id == user_id))
        user: User | None = user_result.scalar_one_or_none()

        tokens_result = await db.execute(
            select(OAuthToken).where(OAuthToken.user_id == user_id)
        )
        tokens = tokens_result.scalars().all()

    connected: dict = {}
    for token in tokens:
        provider_data: dict = {
            "connected": True,
            "username": token.provider_username,
        }
        if token.provider == "google":
            granted = set((token.scope or "").split())
            missing = [
                name
                for name, required in GOOGLE_SCOPE_GROUPS.items()
                if not all(s in granted for s in required)
            ]
            provider_data["scopes"] = token.scope or ""
            provider_data["missing_scopes"] = missing
        connected[token.provider] = provider_data

    email = user.email if user else None
    google_missing = connected.get("google", {}).get("missing_scopes", [])
    logger.info(
        f"User profile loaded for user_id={user_id} ({email}) - "
        f"Linked: {list(connected.keys())}"
        + (f" | Missing scopes: {google_missing}" if google_missing else "")
    )

    return {
        "user_id": str(user_id),
        "email": email,
        "connected_providers": connected,
    }
