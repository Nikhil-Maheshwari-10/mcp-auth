"""
Token repository — the only place in the codebase that reads/writes OAuth tokens.

All other code (MCP tools, auth callbacks) must go through these functions.
Direct DB queries on OAuthToken from outside this module are not allowed.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.logger import logger
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

    username = token_data.get("github_username") or token_data.get("provider_username")

    values = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "provider": provider,
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at,
        "scope": token_data.get("scope"),
        "provider_username": username,
    }

    stmt = pg_insert(OAuthToken).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_oauth_tokens_user_provider",
        set_={
            "access_token": stmt.excluded.access_token,
            "refresh_token": func.coalesce(stmt.excluded.refresh_token, OAuthToken.refresh_token),
            "expires_at": stmt.excluded.expires_at,
            "scope": stmt.excluded.scope,
            "provider_username": stmt.excluded.provider_username,
            "updated_at": datetime.now(tz=timezone.utc),
        },
    )

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(stmt)

    logger.info(f"Saved OAuth token for user {user_id} (provider: {provider}, username: {username})")


async def get_token(user_id: uuid.UUID, provider: str) -> dict[str, Any] | None:
    """Return the stored token dict for a (user, provider) pair, or None if missing.

    Automatically refreshes the token server-side if it is within 5 minutes of
    expiration and a refresh_token is present.
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
            logger.debug(f"No {provider} token found in database for user {user_id}")
            return None

        access_token = row.access_token
        refresh_token = row.refresh_token
        expires_at = row.expires_at
        scope = row.scope
        provider_username = row.provider_username

    # Check if token is expired or within 5 minutes of expiry
    if expires_at is not None and refresh_token:
        time_until_expiry = (expires_at - datetime.now(tz=timezone.utc)).total_seconds()
        if time_until_expiry < 300:  # < 5 minutes
            logger.warning(
                f"{provider} token for user {user_id} expires in {int(time_until_expiry)}s (< 300s) — triggering automatic refresh"
            )
            if provider == "google":
                from api.auth.refresh import refresh_google_token
                try:
                    new_access_token, new_expires_at = await refresh_google_token(refresh_token)
                    await update_token(user_id, provider, new_access_token, new_expires_at)
                    access_token = new_access_token
                    expires_at = new_expires_at
                except Exception as e:
                    logger.error(f"Automatic refresh for Google token failed: {e}")
            elif provider == "github":
                from api.auth.refresh import refresh_github_token
                try:
                    refreshed = await refresh_github_token(refresh_token)
                    if refreshed:
                        new_access_token, new_expires_at = refreshed
                        await update_token(user_id, provider, new_access_token, new_expires_at)
                        access_token = new_access_token
                        expires_at = new_expires_at
                except Exception as e:
                    logger.error(f"Automatic refresh for GitHub token failed: {e}")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "scope": scope,
        "provider": provider,
        "provider_username": provider_username,
    }


async def update_token(
    user_id: uuid.UUID,
    provider: str,
    access_token: str,
    expires_at: datetime | None,
) -> None:
    """Update access_token and expires_at for an existing (user, provider) token."""
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
    logger.info(f"Updated {provider} token in DB for user {user_id}")


async def upsert_user(email: str) -> uuid.UUID:
    """Insert a user by email if they don't exist, return their UUID."""
    stmt = pg_insert(User).values(id=uuid.uuid4(), email=email)
    stmt = stmt.on_conflict_do_update(
        index_elements=["email"],
        set_={"email": stmt.excluded.email},  # no-op update to get RETURNING
    ).returning(User.id)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(stmt)
            user_id = result.scalar_one()

    logger.info(f"User resolved in database: email='{email}', user_id={user_id}")
    return user_id


async def delete_token(user_id: uuid.UUID, provider: str) -> bool:
    """Delete stored OAuth token for a user and provider (e.g. unlinking GitHub)."""
    from sqlalchemy import delete
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                delete(OAuthToken).where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.provider == provider,
                )
            )
            deleted = result.rowcount > 0
    if deleted:
        logger.info(f"Deleted {provider} token from DB for user {user_id}")
    else:
        logger.warning(f"No {provider} token found to delete for user {user_id}")
    return deleted


