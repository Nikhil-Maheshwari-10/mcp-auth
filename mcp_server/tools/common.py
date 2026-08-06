"""
Common helpers for MCP tools — token retrieval from PostgreSQL and header builders.
"""

import os
import uuid
from contextvars import ContextVar
from typing import Any

from core.logger import logger
from db.token_repo import get_token

# ContextVar for setting user_id per request/session in memory
_current_user_id_var: ContextVar[uuid.UUID | None] = ContextVar(
    "current_user_id", default=None
)


def set_context_user_id(user_id: uuid.UUID | str | None) -> None:
    """Set the active user_id for the current context."""
    if isinstance(user_id, str):
        try:
            user_id = uuid.UUID(user_id)
        except ValueError:
            user_id = None
    _current_user_id_var.set(user_id)


def get_user_id_from_context() -> uuid.UUID | None:
    """Extract user_id from context var or environment variable."""
    uid = _current_user_id_var.get()
    if uid:
        return uid
    env_uid = os.environ.get("CURRENT_USER_ID") or os.environ.get("DEFAULT_USER_ID")
    if env_uid:
        try:
            return uuid.UUID(env_uid)
        except ValueError:
            pass
    return None


async def require_token(
    user_id: uuid.UUID | str | None,
    provider: str,
) -> dict[str, Any]:
    """Load valid token for user_id and provider from PostgreSQL via token_repo.

    Automatically refreshes expired/near-expiry tokens via token_repo.get_token.
    Raises RuntimeError with a user-friendly message if no token found or user_id missing.
    """
    from core.messages import TOOL_GOOGLE_TOKEN_MISSING, TOOL_GITHUB_TOKEN_MISSING

    uid: uuid.UUID | None = None
    if user_id:
        if isinstance(user_id, str):
            try:
                uid = uuid.UUID(user_id.strip())
            except ValueError:
                logger.error(f"require_token: invalid user_id UUID string '{user_id}'")
                raise RuntimeError(f"Invalid user_id format: '{user_id}'")
        else:
            uid = user_id
    else:
        uid = get_user_id_from_context()

    if uid is None:
        logger.error("require_token: no user_id in args or context — cannot load OAuth token")
        raise RuntimeError(
            "user_id is required to access OAuth credentials. Please provide user_id."
        )

    token = await get_token(uid, provider)
    if token is None or not token.get("access_token"):
        if provider == "google":
            msg = TOOL_GOOGLE_TOKEN_MISSING
        else:
            msg = TOOL_GITHUB_TOKEN_MISSING
        logger.warning(f"No valid {provider} OAuth token for user {uid} — {msg}")
        raise RuntimeError(msg)
    return token


def build_github_headers(token: dict[str, Any]) -> dict[str, str]:
    """Builds the standard headers needed for GitHub API requests."""
    return {
        "Authorization": f"Bearer {token['access_token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

