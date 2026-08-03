"""
Token repository — the only place in the codebase that reads/writes OAuth tokens.

All other code (MCP tools, auth callbacks) must go through these functions.
Direct DB queries on OAuthToken from outside this module are not allowed.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.engine import AsyncSessionLocal
from db.models import OAuthToken, User


async def save_token(user_id: uuid.UUID, provider: str, token_data: dict[str, Any]) -> None:
    """Upsert a token for a (user, provider) pair.

    If a row already exists for this user + provider, it is replaced.
    token_data must contain at least 'access_token'. Optional keys:
      refresh_token, expires_at (datetime | None), scope (str | None).
    """
    expires_at: datetime | None = token_data.get("expires_at")
    if isinstance(expires_at, (int, float)):
        # Convert Unix timestamp to aware datetime
        expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)

    values = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "provider": provider,
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at,
        "scope": token_data.get("scope"),
    }

    stmt = pg_insert(OAuthToken).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_oauth_tokens_user_provider",
        set_={
            "access_token": stmt.excluded.access_token,
            "refresh_token": stmt.excluded.refresh_token,
            "expires_at": stmt.excluded.expires_at,
            "scope": stmt.excluded.scope,
            "updated_at": datetime.now(tz=timezone.utc),
        },
    )

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(stmt)


async def get_token(user_id: uuid.UUID, provider: str) -> dict[str, Any] | None:
    """Return the stored token dict for a (user, provider) pair, or None if missing.

    Note: token refresh logic will be added in Phase 6c.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OAuthToken).where(
                OAuthToken.user_id == user_id,
                OAuthToken.provider == provider,
            )
        )
        row: OAuthToken | None = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "access_token": row.access_token,
            "refresh_token": row.refresh_token,
            "expires_at": row.expires_at,
            "scope": row.scope,
            "provider": row.provider,
        }


async def update_token(
    user_id: uuid.UUID,
    provider: str,
    access_token: str,
    expires_at: datetime | None,
) -> None:
    """Update access_token and expires_at for an existing (user, provider) token.

    Used by the silent refresh logic in Phase 6c.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                update(OAuthToken)
                .where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.provider == provider,
                )
                .values(
                    access_token=access_token,
                    expires_at=expires_at,
                    updated_at=datetime.now(tz=timezone.utc),
                )
            )


async def upsert_user(email: str) -> uuid.UUID:
    """Insert a user by email if they don't exist, return their UUID.

    Used by auth callbacks when a user logs in for the first time.
    """
    stmt = pg_insert(User).values(id=uuid.uuid4(), email=email)
    stmt = stmt.on_conflict_do_update(
        index_elements=["email"],
        set_={"email": stmt.excluded.email},  # no-op update to get RETURNING
    ).returning(User.id)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(stmt)
            return result.scalar_one()
