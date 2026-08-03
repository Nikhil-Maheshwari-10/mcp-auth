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

import uuid

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth import google as google_auth
from api.auth import github as github_auth
from api.auth.middleware import get_current_user

app = FastAPI(
    title="Workspace Auth API",
    description="Handles OAuth login and session management for the workspace agent.",
    version="0.1.0",
)

# CORS — allows the Vite frontend (phase 6e) to call the API.
# Tighten origins before production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(google_auth.router)
app.include_router(github_auth.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/me")
async def me(user_id: uuid.UUID = Depends(get_current_user)) -> dict:
    """Return the current authenticated user's ID.

    Protected — requires a valid session_id cookie.
    Returns 401 if the cookie is missing or the session has expired.
    """
    return {"user_id": str(user_id)}
