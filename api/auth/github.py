"""
GitHub OAuth2 auth routes.

GET /auth/github/login    — redirect the browser to GitHub's authorization page
GET /auth/github/callback — receive the code, exchange for token, set cookies

Note: GitHub access tokens do not expire by default (no refresh_token needed),
so expires_at is left as None in the DB.
"""

import os
import secrets
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from api.auth.session import create_session
from db.token_repo import upsert_user, save_token
from oauth.common.pkce import generate_code_verifier, generate_code_challenge

load_dotenv()

router = APIRouter(prefix="/auth/github", tags=["auth:github"])

_CLIENT_ID = os.environ["GITHUB_CLIENT_ID"]
_CLIENT_SECRET = os.environ["GITHUB_CLIENT_SECRET"]
_REDIRECT_URI = os.environ["GITHUB_API_REDIRECT_URI"]  # e.g. http://localhost:8001/auth/github/callback
_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

_AUTH_ENDPOINT = "https://github.com/login/oauth/authorize"
_TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"
_USER_URL = "https://api.github.com/user"
_EMAILS_URL = "https://api.github.com/user/emails"

SCOPES = ["read:user", "user:email", "repo", "notifications"]

_pending: dict[str, dict] = {}


@router.get("/login")
async def github_login() -> RedirectResponse:
    """Redirect the browser to GitHub's OAuth authorization page."""
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)

    _pending[state] = {"code_verifier": code_verifier}

    params = {
        "client_id": _CLIENT_ID,
        "redirect_uri": _REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
    }
    return RedirectResponse(f"{_AUTH_ENDPOINT}?{urlencode(params)}")


@router.get("/callback")
async def github_callback(request: Request, code: str, state: str) -> RedirectResponse:
    """Receive the GitHub OAuth callback, exchange code, save token, set cookies."""
    pending = _pending.pop(state, None)
    if pending is None:
        return RedirectResponse(f"{_FRONTEND_URL}/login?error=invalid_state")

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            _TOKEN_ENDPOINT,
            data={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "redirect_uri": _REDIRECT_URI,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

        access_token = token_data["access_token"]
        gh_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # Fetch primary email (email field on /user can be null for private accounts)
        emails_resp = await client.get(_EMAILS_URL, headers=gh_headers)
        emails_resp.raise_for_status()
        emails = emails_resp.json()
        primary_email = next(
            (e["email"] for e in emails if e.get("primary") and e.get("verified")),
            None,
        )
        if primary_email is None:
            return RedirectResponse(f"{_FRONTEND_URL}/login?error=no_verified_email")

    # Upsert user + save token
    user_id = await upsert_user(primary_email)
    await save_token(user_id, "github", {
        "access_token": access_token,
        "refresh_token": None,   # GitHub standard tokens don't expire
        "expires_at": None,
        "scope": token_data.get("scope", ""),
    })

    session_id = await create_session(user_id)

    response = RedirectResponse(url=_FRONTEND_URL)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
    # No github_token_exp cookie since GitHub tokens don't expire
    return response
