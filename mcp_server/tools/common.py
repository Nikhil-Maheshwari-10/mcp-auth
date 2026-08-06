"""
Common helpers for MCP tools — token retrieval from PostgreSQL and header builders.
"""

import hashlib
import json
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

# ── Per-turn deduplication ────────────────────────────────────────────────────
# Tracks (tool_name, args_hash) pairs seen in the current agent turn.
# Stored in a ContextVar so it is isolated per asyncio task (i.e. per ADK turn).
# Reset at the start of each new turn via reset_turn_dedup().
_seen_calls_var: ContextVar[set[str]] = ContextVar("seen_calls", default=set())


def reset_turn_dedup() -> None:
    """Reset the deduplication state for a new agent turn.

    Call this at the start of every new user → agent round-trip so that the
    seen-calls set is cleared and tools can be legitimately called again.
    """
    _seen_calls_var.set(set())


def _call_fingerprint(tool_name: str, args: dict[str, Any]) -> str:
    """Compute a stable fingerprint string for a (tool_name, args) pair."""
    args_str = json.dumps(args, sort_keys=True, default=str)
    args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:16]
    return f"{tool_name}:{args_hash}"


def check_and_mark_call(tool_name: str, args: dict[str, Any]) -> bool:
    """Check if this (tool_name, args) was already executed this turn.

    Returns True if it is a DUPLICATE (should be skipped).
    Returns False if it is NEW (safe to execute — marks it as seen).

    This is the backend safety net that complements the system prompt rule.
    It prevents the LLM from executing the same write action twice in one turn
    even if it hallucinates a duplicate tool call.
    """
    fingerprint = _call_fingerprint(tool_name, args)
    seen = _seen_calls_var.get()
    if fingerprint in seen:
        logger.warning(
            f"[DEDUP] Duplicate tool call blocked: {tool_name}({list(args.items())[:3]!r})"
        )
        return True  # duplicate
    # Mark as seen — copy the set to avoid mutating a shared default
    new_seen = seen | {fingerprint}
    _seen_calls_var.set(new_seen)
    return False  # new call, proceed


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


async def record_audit_log(
    user_id: uuid.UUID | str | None,
    tool_name: str,
    status: str,
    error_msg: str | None = None,
) -> None:
    """Record an entry in audit_logs table for the tool execution."""
    from db.audit_repo import log_tool_call
    uid: uuid.UUID | None = None
    if user_id:
        if isinstance(user_id, str):
            try:
                uid = uuid.UUID(user_id.strip())
            except ValueError:
                pass
        else:
            uid = user_id
    if uid is None:
        uid = get_user_id_from_context()
    if uid:
        await log_tool_call(uid, tool_name, status, error_msg)
