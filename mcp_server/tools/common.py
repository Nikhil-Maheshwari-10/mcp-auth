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
from db.token_repo import get_token, get_token_by_account

# ContextVar for setting user_id and workspace_id per request/session in memory
_current_user_id_var: ContextVar[uuid.UUID | None] = ContextVar("current_user_id", default=None)
_current_workspace_id_var: ContextVar[uuid.UUID | None] = ContextVar("current_workspace_id", default=None)

# Per-turn deduplication
_seen_calls_var: ContextVar[set[str]] = ContextVar("seen_calls", default=set())


def reset_turn_dedup() -> None:
    """Reset the deduplication state for a new agent turn."""
    _seen_calls_var.set(set())


def _call_fingerprint(tool_name: str, args: dict[str, Any]) -> str:
    """Compute a stable fingerprint string for a (tool_name, args) pair."""
    args_str = json.dumps(args, sort_keys=True, default=str)
    args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:16]
    return f"{tool_name}:{args_hash}"


def check_and_mark_call(tool_name: str, args: dict[str, Any]) -> bool:
    """Check if this (tool_name, args) was already executed this turn."""
    fingerprint = _call_fingerprint(tool_name, args)
    seen = _seen_calls_var.get()
    if fingerprint in seen:
        logger.warning(f"[DEDUP] Duplicate tool call blocked: {tool_name}({list(args.items())[:3]!r})")
        return True
    new_seen = seen | {fingerprint}
    _seen_calls_var.set(new_seen)
    return False


def set_context_user_id(user_id: uuid.UUID | str | None) -> None:
    """Set the active user_id for the current context."""
    if isinstance(user_id, str):
        try:
            user_id = uuid.UUID(user_id)
        except ValueError:
            user_id = None
    _current_user_id_var.set(user_id)


def set_context_workspace_id(workspace_id: uuid.UUID | str | None) -> None:
    """Set the active workspace_id for the current context."""
    if isinstance(workspace_id, str):
        try:
            workspace_id = uuid.UUID(workspace_id)
        except ValueError:
            workspace_id = None
    _current_workspace_id_var.set(workspace_id)


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


def get_workspace_id_from_context() -> uuid.UUID | None:
    return _current_workspace_id_var.get()


async def check_account_ambiguity(
    account_email: str,
    provider: str = "google",
) -> str | None:
    """
    If account_email is blank and multiple accounts are connected, return a
    clarification message string. The calling tool should return this immediately
    so the agent tells the user to specify an account — without making any API calls.

    Returns None when it is safe to proceed (single account, or account_email given).
    """
    if account_email and account_email.strip():
        return None  # caller specified an account — proceed

    from db.token_repo import get_all_provider_tokens

    uid = get_user_id_from_context()
    wid = get_workspace_id_from_context()

    if uid is None:
        return None  # no context — let require_token handle it

    # In single-account mode uid == wid; treat workspace_id as None
    effective_wid = wid if (wid is not None and wid != uid) else None

    tokens = await get_all_provider_tokens(uid, provider, workspace_id=effective_wid)
    if len(tokens) < 2:
        return None  # 0 or 1 accounts — no ambiguity

    emails = [t["provider_username"] for t in tokens if t.get("provider_username")]
    accounts_list = "\n".join(f"  • {e}" for e in emails)
    return (
        f"You have {len(emails)} {provider.title()} accounts connected:\n"
        f"{accounts_list}\n\n"
        "Which account would you like to use? You can also say \"all\" to fetch from every account."
    )


async def require_token(
    user_id: uuid.UUID | str | None = None,
    provider: str = "google",
    account_email: str | None = None,
    workspace_id: uuid.UUID | str | None = None,
) -> dict[str, Any]:
    """Load valid token for user_id (and optional workspace_id) from PostgreSQL."""
    from core.messages import TOOL_GOOGLE_TOKEN_MISSING, TOOL_GITHUB_TOKEN_MISSING

    uid: uuid.UUID | None = None
    wid: uuid.UUID | None = None

    # Resolve user_id
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

    # Resolve workspace_id
    if workspace_id:
        if isinstance(workspace_id, str):
            try:
                wid = uuid.UUID(workspace_id.strip())
            except ValueError:
                pass
        else:
            wid = workspace_id
    if wid is None:
        wid = get_workspace_id_from_context()

    if uid is None and wid is None:
        logger.error("require_token: no user_id or workspace_id in args or context")
        raise RuntimeError("Authentication context is required to access tools.")

    # If user_id is missing but wid is given (backwards compat)
    if uid is None and wid is not None:
        uid = wid
        wid = None

    # In single-account mode, get_instruction sets both context vars to the same user_id.
    # Treat uid==wid as "no workspace" so the plain user token (workspace_id IS NULL) is found.
    if uid is not None and wid is not None and uid == wid:
        wid = None

    if account_email and account_email.strip():
        token = await get_token_by_account(uid, provider, account_email.strip(), workspace_id=wid)
        if token is None or not token.get("access_token"):
            # Fetch what IS connected so the LLM can relay a helpful message
            from db.token_repo import get_all_provider_tokens
            connected = await get_all_provider_tokens(uid, provider, workspace_id=wid)
            emails = [t["provider_username"] for t in connected if t.get("provider_username")]
            connected_str = ", ".join(emails) if emails else "none"
            raise RuntimeError(
                f"'{account_email}' is not a connected {provider} account. "
                f"Connected {provider} accounts: {connected_str}. "
                "Please use one of those accounts, or ask the user to connect the account in Settings."
            )
        return token

    token = await get_token(uid, provider, workspace_id=wid)
    if token is None or not token.get("access_token"):
        msg = TOOL_GOOGLE_TOKEN_MISSING if provider == "google" else TOOL_GITHUB_TOKEN_MISSING
        logger.warning(f"No valid {provider} OAuth token for user {uid} (workspace: {wid}) — {msg}")
        raise RuntimeError(msg)
    return token


def build_github_headers(token: dict[str, Any]) -> dict[str, str]:
    """Builds standard headers for GitHub API requests."""
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
    workspace_id: uuid.UUID | str | None = None,
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
