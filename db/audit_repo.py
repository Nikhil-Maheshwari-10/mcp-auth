"""
Audit repository — logs every MCP tool execution to PostgreSQL, scoped to workspace_id.
"""

import uuid
from datetime import datetime, timezone

from core.logger import logger
from db.engine import AsyncSessionLocal
from db.models import AuditLog


async def log_tool_call(
    workspace_id: uuid.UUID,
    tool_name: str,
    status: str,
    error_msg: str | None = None,
) -> None:
    """Log an execution entry to audit_logs table for the workspace."""
    try:
        log_entry = AuditLog(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            tool_name=tool_name,
            status=status,
            error_msg=error_msg,
            called_at=datetime.now(tz=timezone.utc),
        )

        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(log_entry)

        logger.info(f"Audit log saved: tool={tool_name}, workspace={workspace_id}, status={status}")
    except Exception as e:
        logger.error(f"Failed to record audit log for tool '{tool_name}': {e}")
