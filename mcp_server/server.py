"""
FastMCP server entry point — wraps tools/ functions for Claude Desktop and MCP clients.

The tools themselves live in tools/ (framework-agnostic). This file's only job is:
  1. Create the shared FastMCP instance
  2. Import tool functions from tools/ and register them with @mcp.tool
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

from fastmcp import FastMCP

mcp = FastMCP(
    name="personal-workspace-agent",
    instructions=(
        "This server provides authenticated access to Google and GitHub on "
        "behalf of the workspace owner. Always call google_whoami or "
        "github_whoami first to confirm identity before making API calls."
    ),
)

# Import and register all tool functions from the framework-agnostic tools/ package.
# @mcp.tool wraps each function with the MCP JSON-RPC protocol for MCP clients.
import tools.gmail as _gmail
import tools.calendar as _calendar
import tools.github as _github
import inspect

_tool_modules = [_gmail, _calendar, _github]
for _module in _tool_modules:
    for _name, _fn in inspect.getmembers(_module, inspect.iscoroutinefunction):
        if not _name.startswith("_"):
            mcp.tool(_fn)


if __name__ == "__main__":
    import os
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8002"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        # Default stdio mode — for Claude Desktop and local development.
        mcp.run()
