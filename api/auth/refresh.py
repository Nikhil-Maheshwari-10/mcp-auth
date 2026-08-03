"""
Token refresh logic for OAuth providers.

Functions:
  refresh_google_token(refresh_token: str) -> tuple[str, datetime]
  refresh_github_token(refresh_token: str) -> tuple[str, datetime] | None
"""

import os
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

_GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

_GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
_GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
_GITHUB_TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"


async def refresh_google_token(refresh_token: str) -> tuple[str, datetime]:
    """Exchange a Google refresh_token for a fresh access_token.

    Returns:
        tuple of (new_access_token: str, new_expires_at: datetime)
    Raises:
        httpx.HTTPStatusError if Google rejects the refresh request.
    """
    payload = {
        "client_id": _GOOGLE_CLIENT_ID,
        "client_secret": _GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(_GOOGLE_TOKEN_ENDPOINT, data=payload, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

    new_access_token: str = data["access_token"]
    expires_in: int = data.get("expires_in", 3600)
    new_expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)

    return new_access_token, new_expires_at


async def refresh_github_token(refresh_token: str | None) -> tuple[str, datetime] | None:
    """Refresh GitHub token if applicable.

    Standard GitHub OAuth apps issue permanent access tokens without refresh tokens.
    If refresh_token is None or empty, returns None.
    """
    if not refresh_token:
        return None

    payload = {
        "client_id": _GITHUB_CLIENT_ID,
        "client_secret": _GITHUB_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _GITHUB_TOKEN_ENDPOINT,
            data=payload,
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

    if "access_token" not in data:
        return None

    new_access_token: str = data["access_token"]
    expires_in = data.get("expires_in")
    new_expires_at = (
        datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)
        if expires_in
        else None
    )

    return new_access_token, new_expires_at
