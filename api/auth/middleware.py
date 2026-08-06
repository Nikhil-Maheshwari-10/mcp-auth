"""
FastAPI dependency: get_current_user

Reads the `session_id` cookie from the request, looks up the user in the DB,
and returns the user_id UUID. Raises HTTP 401 if missing or invalid.

Usage in any route:
    from api.auth.middleware import get_current_user

    @router.get("/me")
    async def me(user_id: UUID = Depends(get_current_user)):
        ...
"""

import uuid
from fastapi import Cookie
from core.logger import logger
from core.exceptions import UnauthorizedException
from core.messages import AUTH_NOT_AUTHENTICATED, AUTH_SESSION_EXPIRED
from api.auth.session import get_user_from_session


async def get_current_user(
    session_id: str | None = Cookie(default=None),
) -> uuid.UUID:
    """Return the user_id for the current request, or raise 401."""
    if not session_id:
        logger.warning("Authentication failed: missing session_id cookie")
        raise UnauthorizedException(AUTH_NOT_AUTHENTICATED)

    user_id = await get_user_from_session(session_id)
    if user_id is None:
        logger.warning(f"Authentication failed: session '{session_id[:8]}...' expired or invalid")
        raise UnauthorizedException(AUTH_SESSION_EXPIRED)

    logger.debug(f"Authenticated session for user_id={user_id}")
    return user_id

