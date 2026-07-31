"""
FastMCP server entry point for the Personal Workspace Agent.

The FastMCP instance (`mcp`) lives in mcp_server/__init__.py so it is always
a single cached object shared by this file and all tool modules.

This file's only job:
  1. Import the shared mcp instance
  2. Import tool modules so their @mcp.tool decorators fire
  3. Call mcp.run() when executed directly

Run:
    python -m mcp_server.server
    fastmcp dev inspector mcp_server/server.py
"""

import sys
from pathlib import Path

# fastmcp inspector loads this file directly (not as `python -m mcp_server.server`),
# so the project root is not on sys.path yet. Fix that before any local imports.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from mcp_server import mcp  # noqa: F401, E402 — shared FastMCP instance

# Import tool modules so their @mcp.tool decorators fire and register onto mcp.
# These imports MUST come after mcp_server is imported to avoid circular imports.
import mcp_server.tools.gmail  # noqa: F401
import mcp_server.tools.calendar  # noqa: F401
import mcp_server.tools.github  # noqa: F401


if __name__ == "__main__":
    # Runs with stdio transport by default — compatible with Claude Desktop
    # and any MCP client that spawns the server as a subprocess.
    mcp.run()
