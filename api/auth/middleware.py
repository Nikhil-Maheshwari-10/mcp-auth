"""
FastAPI dependencies: get_current_user, get_current_context

get_current_user    — returns user_id
get_current_context — returns (user_id, active_workspace_id | None)
"""

import uuid
from fastapi import Cookie
from core.logger import logger
from core.exceptions import UnauthorizedException
from core.messages import AUTH_NOT_AUTHENTICATED, AUTH_SESSION_EXPIRED
from api.auth.session import get_user_from_session, get_workspace_from_session


async def get_current_user(
    session_id: str | None = Cookie(default=None),
) -> uuid.UUID:
    """Return the user_id for the current request, or raise 401."""
    if not session_id:
        raise UnauthorizedException(AUTH_NOT_AUTHENTICATED)

    user_id = await get_user_from_session(session_id)
    if user_id is None:
        raise UnauthorizedException(AUTH_SESSION_EXPIRED)

    return user_id


async def get_current_context(
    session_id: str | None = Cookie(default=None),
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Return (user_id, active_workspace_id | None) for the current request.

    workspace_id will be None if the user is in standard single account mode.
    """
    if not session_id:
        raise UnauthorizedException(AUTH_NOT_AUTHENTICATED)

    user_id = await get_user_from_session(session_id)
    if user_id is None:
        raise UnauthorizedException(AUTH_SESSION_EXPIRED)

    workspace_id = await get_workspace_from_session(session_id)
    return user_id, workspace_id
