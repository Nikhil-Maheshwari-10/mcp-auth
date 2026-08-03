"""
Session management — create sessions and look up user from session_id.

Sessions are stored in the DB (Session table). The session_id is a UUID
issued as an HttpOnly cookie to the browser.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.engine import AsyncSessionLocal
from db.models import Session


async def create_session(user_id: uuid.UUID) -> str:
    """Create a new session for user_id and return the session_id string."""
    session_id = uuid.uuid4()
    stmt = pg_insert(Session).values(
        id=session_id,
        user_id=user_id,
        created_at=datetime.now(tz=timezone.utc),
        last_seen=datetime.now(tz=timezone.utc),
    )
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(stmt)
    return str(session_id)


async def get_user_from_session(session_id: str) -> uuid.UUID | None:
    """Return the user_id for a session_id, or None if not found."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return None

    async with AsyncSessionLocal() as db:
        async with db.begin():
            result = await db.execute(
                select(Session).where(Session.id == sid)
            )
            row: Session | None = result.scalar_one_or_none()
            if row is None:
                return None

            row.last_seen = datetime.now(tz=timezone.utc)
            return row.user_id
