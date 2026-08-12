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
from core.logger import logger

load_dotenv()

_GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

_GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
_GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
_GITHUB_TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"


async def refresh_google_token(refresh_token: str) -> tuple[str, datetime, str | None]:
    """Exchange a Google refresh_token for a fresh access_token.

    Returns:
        tuple of (new_access_token: str, new_expires_at: datetime, new_refresh_token: str | None)
    Raises:
        httpx.HTTPStatusError if Google rejects the refresh request.
    """
    logger.info("Executing silent Google OAuth token refresh...")
    payload = {
        "client_id": _GOOGLE_CLIENT_ID,
        "client_secret": _GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(_GOOGLE_TOKEN_ENDPOINT, data=payload, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()

        new_access_token: str = data["access_token"]
        expires_in: int = data.get("expires_in", 3600)
        new_expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)
        new_refresh_token: str | None = data.get("refresh_token")

        logger.success(f"Google token refreshed successfully (expires in {expires_in}s at {new_expires_at.strftime('%H:%M:%S')})")
        return new_access_token, new_expires_at, new_refresh_token
    except Exception as exc:
        logger.error(f"Google token refresh failed: {exc}")
        raise


async def refresh_github_token(refresh_token: str | None) -> tuple[str, datetime] | None:
    """Refresh GitHub token if applicable.

    Standard GitHub OAuth apps issue permanent access tokens without refresh tokens.
    If refresh_token is None or empty, returns None.
    """
    if not refresh_token:
        return None

    logger.info("Executing silent GitHub OAuth token refresh...")
    payload = {
        "client_id": _GITHUB_CLIENT_ID,
        "client_secret": _GITHUB_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
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
            logger.warning("GitHub refresh response missing access_token")
            return None

        new_access_token: str = data["access_token"]
        expires_in = data.get("expires_in")
        new_expires_at = (
            datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)
            if expires_in
            else None
        )

        logger.success("GitHub token refreshed successfully")
        return new_access_token, new_expires_at
    except Exception as exc:
        logger.error(f"GitHub token refresh failed: {exc}")
        return None

