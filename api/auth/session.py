"""
Session management — create sessions and look up user+workspace from session_id.

Sessions are stored in the DB (Session table). The session_id is a UUID
issued as an HttpOnly cookie to the browser.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.logger import logger
from db.engine import AsyncSessionLocal
from db.models import Session


async def create_session(user_id: uuid.UUID, workspace_id: uuid.UUID | None = None) -> str:
    """Create a new session for user_id and optional workspace_id, return session_id string."""
    session_id = uuid.uuid4()
    stmt = pg_insert(Session).values(
        id=session_id,
        user_id=user_id,
        active_workspace_id=workspace_id,
        created_at=datetime.now(tz=timezone.utc),
        last_seen=datetime.now(tz=timezone.utc),
    )
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(stmt)
    logger.info(f"Created browser session {session_id} for user {user_id} (workspace: {workspace_id})")
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


async def get_workspace_from_session(session_id: str) -> uuid.UUID | None:
    """Return the active_workspace_id for a session_id, or None if not found."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Session.active_workspace_id).where(Session.id == sid)
        )
        return result.scalar_one_or_none()


async def switch_workspace_in_session(session_id: str, workspace_id: uuid.UUID | None) -> bool:
    """Update active_workspace_id on an existing session. Returns True if updated."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return False

    async with AsyncSessionLocal() as db:
        async with db.begin():
            result = await db.execute(
                update(Session)
                .where(Session.id == sid)
                .values(active_workspace_id=workspace_id, last_seen=datetime.now(tz=timezone.utc))
                .returning(Session.id)
            )
            updated = result.scalar_one_or_none()

    if updated:
        logger.info(f"Session {sid} switched active workspace to {workspace_id}")
    return updated is not None


async def delete_session(session_id: str) -> None:
    """Delete a session from the DB by session_id."""
    from sqlalchemy import delete
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(delete(Session).where(Session.id == sid))
    logger.info(f"Deleted browser session {sid} from DB")
