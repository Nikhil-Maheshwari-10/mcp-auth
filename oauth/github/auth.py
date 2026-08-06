"""
oauth/github/auth.py — Core GitHub OAuth2 logic.

Pure functions — no FastAPI, no HTTP request objects.
Called by api/auth/github.py (FastAPI routes) and usable in tests independently.

Public API:
    SCOPES                 — list of GitHub OAuth scopes requested
    build_auth_url(...)    — constructs the GitHub authorization URL
    exchange_code(...)     — exchanges an auth code for access_token + github_username
"""

import os
import secrets
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv

from core.logger import logger

load_dotenv()

# ── OAuth Endpoints ────────────────────────────────────────────────────────────

AUTH_ENDPOINT = "https://github.com/login/oauth/authorize"
TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"

# ── OAuth Scopes ───────────────────────────────────────────────────────────────

SCOPES = ["read:user", "user:email", "repo", "notifications"]

# ── Credentials (read once at import time) ─────────────────────────────────────

CLIENT_ID: str = os.environ["GITHUB_CLIENT_ID"]
CLIENT_SECRET: str = os.environ["GITHUB_CLIENT_SECRET"]


# ── Core Functions ─────────────────────────────────────────────────────────────

def build_auth_url(redirect_uri: str, state: str) -> str:
    """Build the GitHub OAuth authorization URL.

    Args:
        redirect_uri: Where GitHub should send the user after consent.
        state:        Opaque CSRF state token.

    Returns:
        Full authorization URL to redirect the browser to.
    """
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


def generate_state() -> str:
    """Generate a fresh CSRF state token."""
    return secrets.token_urlsafe(16)


async def exchange_code(code: str, redirect_uri: str) -> tuple[str, str]:
    """Exchange a GitHub authorization code for an access token and username.

    Args:
        code:         The authorization code received from GitHub's callback.
        redirect_uri: Must exactly match the redirect_uri used in the auth URL.

    Returns:
        (access_token, github_username)

    Raises:
        ValueError: If GitHub returned an error in the token response.
        httpx.HTTPStatusError: On non-2xx HTTP response from GitHub.
        Exception: On network or unexpected error.
    """
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            TOKEN_ENDPOINT,
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

        if "error" in token_data:
            raise ValueError(
                f"GitHub token exchange error: {token_data.get('error_description', token_data['error'])}"
            )

        access_token: str = token_data["access_token"]

        # Fetch GitHub username
        user_resp = await client.get(
            USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_resp.raise_for_status()
        user_info = user_resp.json()
        github_username: str = user_info.get("login", "")

    logger.debug(f"[GITHUB AUTH] Token exchange successful for '@{github_username}'")
    return access_token, github_username
