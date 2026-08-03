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

from fastapi import Cookie, Depends, HTTPException, status

from api.auth.session import get_user_from_session


async def get_current_user(
    session_id: str | None = Cookie(default=None),
) -> uuid.UUID:
    """Return the user_id for the current request, or raise 401."""
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated — no session cookie.",
        )

    user_id = await get_user_from_session(session_id)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid.",
        )

    return user_id
