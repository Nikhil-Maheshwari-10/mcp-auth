"""
db/workspace_repo.py — All DB operations related to Workspaces.

This is the single source of truth for workspace CRUD, user-workspace membership,
and workspace selection during login and session switching.

Design principles:
  - Workspaces are the primary isolation boundary — all tokens and chat history belong to them.
  - One User (login identity) can own multiple Workspaces.
  - The same email can be an OAuth tool token in multiple workspaces without conflict.
  - ADK chat history is scoped to workspace_id (passed as ADK's user_id field).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update

from core.logger import logger
from db.engine import AsyncSessionLocal
from db.models import OAuthToken, Session, User, Workspace, WorkspaceUser


async def create_workspace(name: str) -> uuid.UUID:
    """Create a new Workspace row and return its id."""
    workspace_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        async with db.begin():
            db.add(Workspace(id=workspace_id, name=name[:120]))
    logger.info(f"Created new workspace '{name}' (id={workspace_id})")
    return workspace_id


async def add_user_to_workspace(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str = "owner",
) -> None:
    """Link a User login identity to a Workspace with the given role."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            existing = await db.execute(
                select(WorkspaceUser).where(
                    WorkspaceUser.workspace_id == workspace_id,
                    WorkspaceUser.user_id == user_id,
                )
            )
            if existing.scalar_one_or_none() is None:
                db.add(WorkspaceUser(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role=role,
                ))
    logger.info(f"User {user_id} linked to workspace {workspace_id} as '{role}'")


async def get_workspaces_for_user(user_id: uuid.UUID) -> list[dict]:
    """
    Return all workspaces this user is a member of, ordered by creation date (newest first).

    Each entry: {id, name, created_at, role, account_count}
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workspace, WorkspaceUser.role)
            .join(WorkspaceUser, WorkspaceUser.workspace_id == Workspace.id)
            .where(WorkspaceUser.user_id == user_id)
            .order_by(Workspace.created_at.desc())
        )
        rows = result.all()

    workspaces = []
    for workspace, role in rows:
        # Count connected OAuth accounts in this workspace
        async with AsyncSessionLocal() as db:
            count_result = await db.execute(
                select(OAuthToken).where(OAuthToken.workspace_id == workspace.id)
            )
            account_count = len(count_result.scalars().all())

        workspaces.append({
            "id": str(workspace.id),
            "name": workspace.name,
            "created_at": workspace.created_at.isoformat(),
            "role": role,
            "account_count": account_count,
        })

    return workspaces


async def get_workspace_by_id(workspace_id: uuid.UUID) -> dict | None:
    """Return workspace metadata dict or None if not found."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = result.scalar_one_or_none()

    if workspace is None:
        return None

    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "created_at": workspace.created_at.isoformat(),
    }


async def get_or_create_default_workspace(user_id: uuid.UUID, display_name: str) -> uuid.UUID:
    """
    Find the workspace this user owns (role='owner').
    If none exists, create one named from display_name and link user as owner.

    Returns workspace_id.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workspace)
            .join(WorkspaceUser, WorkspaceUser.workspace_id == Workspace.id)
            .where(
                WorkspaceUser.user_id == user_id,
                WorkspaceUser.role == "owner",
            )
            .order_by(Workspace.created_at.asc())  # oldest = their original workspace
        )
        workspace = result.scalars().first()

    if workspace is not None:
        logger.info(f"Found existing workspace '{workspace.name}' ({workspace.id}) for user {user_id}")
        return workspace.id

    # No workspace exists — create a fresh one
    workspace_name = display_name.split("@")[0].replace(".", " ").title() + "'s Workspace"
    workspace_id = await create_workspace(workspace_name)
    await add_user_to_workspace(workspace_id, user_id, role="owner")
    logger.info(f"Created default workspace '{workspace_name}' for user {user_id}")
    return workspace_id


async def get_workspace_id_by_provider_sub(provider: str, provider_sub: str) -> uuid.UUID | None:
    """
    Find which workspace holds an OAuth token for this stable provider sub (Google sub / GitHub ID).

    Used during login to identify the user's existing workspace from their Google account.
    Returns the workspace_id of the first match (ordered by workspace creation date, oldest first).
    This is deterministic — provider_sub is stable and immutable for each Google account.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(OAuthToken.workspace_id)
            .where(
                OAuthToken.provider == provider,
                OAuthToken.provider_account_id == provider_sub,
            )
            .order_by(OAuthToken.updated_at.asc())  # oldest token = the original workspace
            .limit(1)
        )
        return result.scalar_one_or_none()


async def switch_active_workspace(session_id: str, workspace_id: uuid.UUID) -> bool:
    """
    Update the active_workspace_id on an existing session.
    Returns True if the session was found and updated.
    """
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        logger.warning(f"switch_active_workspace: invalid session_id '{session_id}'")
        return False

    async with AsyncSessionLocal() as db:
        async with db.begin():
            result = await db.execute(
                update(Session)
                .where(Session.id == sid)
                .values(active_workspace_id=workspace_id)
                .returning(Session.id)
            )
            updated = result.scalar_one_or_none()

    if updated:
        logger.info(f"Session {sid} switched to workspace {workspace_id}")
    else:
        logger.warning(f"switch_active_workspace: session {sid} not found")
    return updated is not None


async def delete_workspace(workspace_id: uuid.UUID) -> None:
    """
    Delete a workspace and all its cascade children (tokens, audit logs).
    The cascade is handled by the DB FK constraints (ondelete='CASCADE').
    """
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(delete(Workspace).where(Workspace.id == workspace_id))
    logger.info(f"Deleted workspace {workspace_id} and all its cascade data")


async def user_is_workspace_member(user_id: uuid.UUID, workspace_id: uuid.UUID) -> bool:
    """Return True if the user is a member (owner or otherwise) of the workspace."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorkspaceUser).where(
                WorkspaceUser.user_id == user_id,
                WorkspaceUser.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none() is not None


async def get_owner_user_id_for_workspace(workspace_id: uuid.UUID) -> uuid.UUID | None:
    """
    Return the owner user_id for a workspace.

    Tokens are always stored with the real user_id (login identity), but in workspace
    mode the ADK session uses workspace_id as ctx.user_id. This function resolves the
    actual user_id so token lookups work correctly.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorkspaceUser.user_id)
            .where(
                WorkspaceUser.workspace_id == workspace_id,
                WorkspaceUser.role == "owner",
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

