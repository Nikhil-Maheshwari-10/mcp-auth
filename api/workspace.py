"""
api/workspace.py — Workspace management routes.

Routes:
  GET  /workspace/list     — list all workspaces the current user has access to
  GET  /workspace/current  — get info about the currently active workspace
  POST /workspace/switch   — switch to a different workspace (updates session)
  POST /workspace/create   — create a new workspace and switch into it
  DELETE /workspace/{workspace_id} — delete a workspace + all its data
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.logger import logger
from api.auth.middleware import get_current_context
from api.auth.session import switch_workspace_in_session
from db.workspace_repo import (
    create_workspace,
    add_user_to_workspace,
    get_workspaces_for_user,
    get_workspace_by_id,
    delete_workspace,
    user_is_workspace_member,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/list")
async def list_workspaces(ctx: tuple = Depends(get_current_context)) -> list[dict]:
    """List all workspaces the current user is a member of."""
    user_id, _ = ctx
    workspaces = await get_workspaces_for_user(user_id)
    return workspaces


@router.get("/current")
async def current_workspace(ctx: tuple = Depends(get_current_context)) -> dict:
    """Return metadata about the currently active workspace."""
    _, workspace_id = ctx
    workspace = await get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Active workspace not found")
    return workspace


@router.post("/switch")
async def switch_workspace_route(
    request: Request,
    ctx: tuple = Depends(get_current_context),
) -> JSONResponse:
    """Switch the session's active workspace.

    Body: {"workspace_id": "<uuid>"}

    The user must already be a member of the target workspace.
    """
    user_id, current_workspace_id = ctx
    session_id = request.cookies.get("session_id")

    try:
        body = await request.json()
    except Exception:
        body = {}

    ws_id_val = body.get("workspace_id")
    if not ws_id_val or ws_id_val == "none":
        await switch_workspace_in_session(session_id, None)
        logger.info(f"User {user_id} switched back to default single-account mode")
        return JSONResponse({"status": "switched", "workspace_id": None})

    try:
        target_workspace_id = uuid.UUID(ws_id_val)
    except Exception:
        return JSONResponse({"error": "Invalid workspace_id format"}, status_code=400)

    # Verify user is a member of the target workspace
    is_member = await user_is_workspace_member(user_id, target_workspace_id)
    if not is_member:
        logger.warning(f"User {user_id} tried to switch to non-member workspace {target_workspace_id}")
        raise HTTPException(status_code=403, detail="Not a member of that workspace")

    success = await switch_workspace_in_session(session_id, target_workspace_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to switch workspace")

    logger.info(f"User {user_id} switched from workspace {current_workspace_id} to {target_workspace_id}")
    return JSONResponse({"status": "switched", "workspace_id": str(target_workspace_id)})


@router.post("/create")
async def create_workspace_route(
    request: Request,
    ctx: tuple = Depends(get_current_context),
) -> JSONResponse:
    """Create a new workspace and immediately switch the session into it.

    Body: {"name": "My New Workspace"}
    """
    user_id, _ = ctx
    session_id = request.cookies.get("session_id")

    try:
        body = await request.json()
        name = (body.get("name") or "My Workspace")[:120].strip()
    except Exception:
        name = "My Workspace"

    if not name:
        name = "My Workspace"

    workspace_id = await create_workspace(name)
    await add_user_to_workspace(workspace_id, user_id, role="owner")

    # Copy primary Google token to new workspace so primary account is active in new workspace
    from db.token_repo import get_token, save_token
    primary_token = await get_token(user_id, "google", workspace_id=None)
    if primary_token:
        await save_token(user_id, "google", primary_token, workspace_id=workspace_id)

    # Also copy the primary GitHub token (if any) to the new workspace
    primary_github = await get_token(user_id, "github", workspace_id=None)
    if primary_github:
        await save_token(user_id, "github", primary_github, workspace_id=workspace_id)
        logger.info(f"Copied primary GitHub token to new workspace {workspace_id}")

    await switch_workspace_in_session(session_id, workspace_id)

    logger.info(f"User {user_id} created and switched to new workspace '{name}' ({workspace_id})")
    return JSONResponse({"workspace_id": str(workspace_id), "name": name})


@router.delete("/{workspace_id_str}")
async def delete_workspace_route(
    workspace_id_str: str,
    request: Request,
    ctx: tuple = Depends(get_current_context),
) -> JSONResponse:
    """Permanently delete a workspace and all its data (tokens, audit logs, ADK chat history).

    The user must own this workspace. Cannot be undone.
    Also wipes all ADK chat sessions scoped to this workspace.
    """
    user_id, current_workspace_id = ctx
    session_id = request.cookies.get("session_id")

    try:
        target_id = uuid.UUID(workspace_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace_id")

    # Verify ownership
    is_member = await user_is_workspace_member(user_id, target_id)
    if not is_member:
        raise HTTPException(status_code=403, detail="You do not own this workspace")

    # Wipe ADK chat sessions for this workspace via direct SQL
    # (events cascade-deleted by FK ON DELETE CASCADE)
    try:
        from db.engine import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await db.execute(
                    text("DELETE FROM sessions WHERE app_name = 'adk_agent' AND user_id = :uid"),
                    {"uid": str(target_id)},
                )
        logger.info(f"Wiped ADK chat history for workspace {target_id}")
    except Exception as e:
        logger.warning(f"Could not wipe ADK sessions for workspace {target_id}: {e}")

    # Delete workspace (cascade: tokens + audit logs via FK)
    await delete_workspace(target_id)

    # If deleting the currently active workspace, switch session to another workspace or single-account mode
    switched_to: str | None = None
    if target_id == current_workspace_id:
        remaining = await get_workspaces_for_user(user_id)
        if remaining and len(remaining) > 0:
            next_ws_id = uuid.UUID(remaining[0]["id"])
            await switch_workspace_in_session(session_id, next_ws_id)
            switched_to = str(next_ws_id)
            logger.info(f"Deleted active workspace {target_id}, automatically switched session to remaining workspace {next_ws_id}")
        else:
            await switch_workspace_in_session(session_id, None)
            switched_to = None
            logger.info(f"Deleted active workspace {target_id}, no remaining workspaces — switched session to single account mode")

    return JSONResponse({"status": "deleted", "active_switched": target_id == current_workspace_id, "switched_to": switched_to})
