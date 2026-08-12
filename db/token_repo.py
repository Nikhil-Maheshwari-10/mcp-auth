"""
Token repository — the only place in the codebase that reads/writes OAuth tokens.

All other code (MCP tools, auth callbacks) must go through these functions.
Direct DB queries on OAuthToken from outside this module are not allowed.

Multi-account + Optional Workspace support:
  - Tokens always belong to user_id.
  - Optionally associated with workspace_id if inside a custom workspace.
  - ALL accounts within a user scope or workspace scope are available.
  - Tools specify which account to use via account_email (provider_username).
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.logger import logger
from db.engine import AsyncSessionLocal
from db.models import OAuthToken, User


# ─── Fernet Encryption Helpers ───────────────────────────────────────────────

def _get_fernet() -> Fernet | None:
    key = os.getenv("FERNET_KEY", "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception as e:
        logger.error(f"Invalid FERNET_KEY in environment: {e}")
        return None


def _encrypt(val: str | None) -> str | None:
    if not val:
        return val
    f = _get_fernet()
    if not f:
        return val
    try:
        return f.encrypt(val.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to encrypt token: {e}")
        return val


def _decrypt(val: str | None) -> str | None:
    if not val:
        return val
    f = _get_fernet()
    if not f:
        return val
    try:
        return f.decrypt(val.encode()).decode()
    except Exception:
        return val


def _row_to_dict(row: OAuthToken) -> dict[str, Any]:
    """Convert an OAuthToken row to a plain dict with decrypted tokens."""
    return {
        "access_token": _decrypt(row.access_token),
        "refresh_token": _decrypt(row.refresh_token),
        "expires_at": row.expires_at,
        "scope": row.scope,
        "provider": row.provider,
        "provider_username": row.provider_username,
        "provider_account_id": row.provider_account_id,
        "is_active": row.is_active,
        "avatar_url": row.avatar_url,
    }


async def _auto_refresh_if_needed(token_dict: dict, user_id: uuid.UUID, provider: str, workspace_id: uuid.UUID | None = None) -> dict:
    """Check if a token is near expiry and refresh it server-side if possible."""
    expires_at = token_dict.get("expires_at")
    refresh_token = token_dict.get("refresh_token")
    account_id = token_dict.get("provider_account_id")

    if expires_at is None or not refresh_token:
        return token_dict

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    time_until_expiry = (expires_at - datetime.now(tz=timezone.utc)).total_seconds()
    if time_until_expiry >= 300:
        return token_dict

    logger.warning(
        f"{provider} token for user {user_id} (workspace: {workspace_id}) expires in "
        f"{int(time_until_expiry)}s (<300s) — triggering automatic refresh"
    )

    if provider == "google":
        from api.auth.refresh import refresh_google_token
        try:
            new_access_token, new_expires_at, new_refresh_token = await refresh_google_token(refresh_token)
            await update_token(user_id, provider, new_access_token, new_expires_at, account_id, workspace_id, new_refresh_token)
            token_dict["access_token"] = new_access_token
            token_dict["expires_at"] = new_expires_at
            if new_refresh_token:
                token_dict["refresh_token"] = new_refresh_token
        except Exception as e:
            logger.error(f"Automatic refresh for Google token failed: {e}")
    elif provider == "github":
        from api.auth.refresh import refresh_github_token
        try:
            refreshed = await refresh_github_token(refresh_token)
            if refreshed:
                new_access_token, new_expires_at = refreshed
                await update_token(user_id, provider, new_access_token, new_expires_at, account_id, workspace_id)
                token_dict["access_token"] = new_access_token
                token_dict["expires_at"] = new_expires_at
        except Exception as e:
            logger.error(f"Automatic refresh for GitHub token failed: {e}")

    return token_dict


# ─── Public API ──────────────────────────────────────────────────────────────

async def save_token(
    user_id: uuid.UUID,
    provider: str,
    token_data: dict[str, Any],
    workspace_id: uuid.UUID | None = None,
) -> None:
    """Save an encrypted token for a user (and optional workspace)."""
    expires_at: datetime | None = token_data.get("expires_at")
    if isinstance(expires_at, (int, float)):
        expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)

    username = token_data.get("provider_username") or token_data.get("github_username")
    account_id = token_data.get("provider_account_id") or username or str(uuid.uuid4())

    raw_access = token_data["access_token"]
    raw_refresh = token_data.get("refresh_token")

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Check for existing token row
            conditions = [
                OAuthToken.user_id == user_id,
                OAuthToken.provider == provider,
                OAuthToken.provider_account_id == account_id,
            ]
            if workspace_id:
                conditions.append(OAuthToken.workspace_id == workspace_id)
            else:
                conditions.append(OAuthToken.workspace_id.is_(None))

            result = await session.execute(select(OAuthToken).where(*conditions))
            existing = result.scalar_one_or_none()

            if existing:
                existing.access_token = _encrypt(raw_access)
                if raw_refresh:
                    existing.refresh_token = _encrypt(raw_refresh)
                existing.expires_at = expires_at
                existing.scope = token_data.get("scope")
                existing.provider_username = username
                if token_data.get("avatar_url"):
                    existing.avatar_url = token_data.get("avatar_url")
                existing.is_active = True
                existing.updated_at = datetime.now(tz=timezone.utc)
            else:
                new_token = OAuthToken(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    workspace_id=workspace_id,
                    provider=provider,
                    provider_account_id=account_id,
                    is_active=True,
                    access_token=_encrypt(raw_access),
                    refresh_token=_encrypt(raw_refresh) if raw_refresh else None,
                    expires_at=expires_at,
                    scope=token_data.get("scope"),
                    provider_username=username,
                    avatar_url=token_data.get("avatar_url"),
                )
                session.add(new_token)

            # Set all other accounts for this scope to inactive
            other_conditions = [
                OAuthToken.user_id == user_id,
                OAuthToken.provider == provider,
                OAuthToken.provider_account_id != account_id,
            ]
            if workspace_id:
                other_conditions.append(OAuthToken.workspace_id == workspace_id)
            else:
                other_conditions.append(OAuthToken.workspace_id.is_(None))

            await session.execute(
                update(OAuthToken)
                .where(*other_conditions)
                .values(is_active=False)
            )

    logger.info(
        f"Saved OAuth token for user {user_id} (workspace: {workspace_id}, provider: {provider}, username: {username})"
    )


async def get_token(
    user_id: uuid.UUID,
    provider: str,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """Return the active token for a user and optional workspace."""
    async with AsyncSessionLocal() as session:
        conditions = [OAuthToken.user_id == user_id, OAuthToken.provider == provider]
        if workspace_id:
            conditions.append(OAuthToken.workspace_id == workspace_id)
        else:
            conditions.append(OAuthToken.workspace_id.is_(None))

        result = await session.execute(
            select(OAuthToken).where(*conditions).order_by(OAuthToken.is_active.desc())
        )
        rows = result.scalars().all()

        if not rows and workspace_id:
            fallback_conditions = [
                OAuthToken.user_id == user_id,
                OAuthToken.provider == provider,
                OAuthToken.workspace_id.is_(None),
            ]
            result = await session.execute(
                select(OAuthToken).where(*fallback_conditions).order_by(OAuthToken.is_active.desc())
            )
            rows = result.scalars().all()

    if not rows:
        return None

    row = rows[0]
    token_dict = _row_to_dict(row)
    return await _auto_refresh_if_needed(token_dict, user_id, provider, workspace_id)


async def get_token_by_account(
    user_id: uuid.UUID,
    provider: str,
    account_email: str,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """Return token for a specific account identified by email/username."""
    async with AsyncSessionLocal() as session:
        conditions = [
            OAuthToken.user_id == user_id,
            OAuthToken.provider == provider,
            OAuthToken.provider_username == account_email,
        ]
        if workspace_id:
            conditions.append(OAuthToken.workspace_id == workspace_id)
        else:
            conditions.append(OAuthToken.workspace_id.is_(None))

        result = await session.execute(select(OAuthToken).where(*conditions))
        row = result.scalar_one_or_none()

        if row is None and workspace_id:
            fallback_conditions = [
                OAuthToken.user_id == user_id,
                OAuthToken.provider == provider,
                OAuthToken.provider_username == account_email,
                OAuthToken.workspace_id.is_(None),
            ]
            result = await session.execute(select(OAuthToken).where(*fallback_conditions))
            row = result.scalar_one_or_none()

    if row is None:
        return None

    token_dict = _row_to_dict(row)
    return await _auto_refresh_if_needed(token_dict, user_id, provider, workspace_id)


async def get_all_provider_tokens(
    user_id: uuid.UUID,
    provider: str,
    workspace_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Return all linked accounts for a user / workspace."""
    async with AsyncSessionLocal() as session:
        conditions = [OAuthToken.user_id == user_id, OAuthToken.provider == provider]
        if workspace_id:
            conditions.append(OAuthToken.workspace_id == workspace_id)
        else:
            conditions.append(OAuthToken.workspace_id.is_(None))

        result = await session.execute(
            select(OAuthToken).where(*conditions).order_by(OAuthToken.is_active.desc())
        )
        rows = result.scalars().all()

        if not rows and workspace_id:
            fallback_conditions = [
                OAuthToken.user_id == user_id,
                OAuthToken.provider == provider,
                OAuthToken.workspace_id.is_(None),
            ]
            result = await session.execute(
                select(OAuthToken).where(*fallback_conditions).order_by(OAuthToken.is_active.desc())
            )
            rows = result.scalars().all()

    return [
        {
            "provider_account_id": row.provider_account_id,
            "provider_username": row.provider_username,
            "avatar_url": row.avatar_url,
            "scope": row.scope,
            "is_active": row.is_active,
            "expires_at": row.expires_at,
        }
        for row in rows
    ]


async def update_token(
    user_id: uuid.UUID,
    provider: str,
    access_token: str,
    expires_at: datetime | None,
    provider_account_id: str | None = None,
    workspace_id: uuid.UUID | None = None,
    refresh_token: str | None = None,
) -> None:
    """Update access_token, expires_at, and optional new refresh_token."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            conditions = [OAuthToken.user_id == user_id, OAuthToken.provider == provider]
            if workspace_id:
                conditions.append(OAuthToken.workspace_id == workspace_id)
            else:
                conditions.append(OAuthToken.workspace_id.is_(None))

            if provider_account_id:
                conditions.append(OAuthToken.provider_account_id == provider_account_id)
            else:
                conditions.append(OAuthToken.is_active == True)

            values_to_update: dict[str, Any] = {
                "access_token": _encrypt(access_token),
                "expires_at": expires_at,
                "updated_at": datetime.now(tz=timezone.utc),
            }
            if refresh_token:
                values_to_update["refresh_token"] = _encrypt(refresh_token)

            await session.execute(
                update(OAuthToken)
                .where(*conditions)
                .values(**values_to_update)
            )


async def upsert_user(email: str) -> uuid.UUID:
    """Insert a user by email if they don't exist, return their UUID."""
    stmt = pg_insert(User).values(id=uuid.uuid4(), email=email)
    stmt = stmt.on_conflict_do_update(
        index_elements=["email"],
        set_={"email": stmt.excluded.email},
    ).returning(User.id)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(stmt)
            user_id = result.scalar_one()

    return user_id


async def upsert_user_by_sub(sub: str, email: str) -> uuid.UUID:
    """Find or create a User by stable Google sub."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(select(User).where(User.google_sub == sub))
            existing_user = result.scalar_one_or_none()

            if existing_user is not None:
                if existing_user.email != email:
                    existing_user.email = email
                return existing_user.id

            result = await session.execute(select(User).where(User.email == email))
            email_user = result.scalar_one_or_none()

            if email_user is not None:
                email_user.google_sub = sub
                return email_user.id

            new_user = User(id=uuid.uuid4(), email=email, google_sub=sub)
            session.add(new_user)
            await session.flush()
            user_id = new_user.id

    return user_id


async def delete_token(
    user_id: uuid.UUID,
    provider: str,
    provider_account_id: str | None = None,
    workspace_id: uuid.UUID | None = None,
) -> bool:
    """Delete a stored OAuth token."""
    from sqlalchemy import delete as sa_delete
    async with AsyncSessionLocal() as session:
        async with session.begin():
            conditions = [OAuthToken.user_id == user_id, OAuthToken.provider == provider]
            if workspace_id:
                conditions.append(OAuthToken.workspace_id == workspace_id)
            else:
                conditions.append(OAuthToken.workspace_id.is_(None))

            if provider_account_id:
                conditions.append(OAuthToken.provider_account_id == provider_account_id)

            result = await session.execute(sa_delete(OAuthToken).where(*conditions))
            deleted = result.rowcount > 0

    return deleted


async def set_active_token(
    user_id: uuid.UUID,
    provider: str,
    provider_account_id: str,
    workspace_id: uuid.UUID | None = None,
) -> bool:
    """Set a specific account as active."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            conditions = [
                OAuthToken.user_id == user_id,
                OAuthToken.provider == provider,
            ]
            if workspace_id:
                conditions.append(OAuthToken.workspace_id == workspace_id)
            else:
                conditions.append(OAuthToken.workspace_id.is_(None))

            # Set all to inactive
            await session.execute(update(OAuthToken).where(*conditions).values(is_active=False))

            # Set target active
            target_conditions = conditions + [OAuthToken.provider_account_id == provider_account_id]
            res = await session.execute(update(OAuthToken).where(*target_conditions).values(is_active=True))
            return res.rowcount > 0
