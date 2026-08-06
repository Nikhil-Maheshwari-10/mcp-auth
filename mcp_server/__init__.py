"""
mcp_server — FastMCP server for the Personal Workspace Agent.

The shared `mcp` instance lives here so that both server.py and all tool
modules import from the same cached location, regardless of how server.py
was loaded (python -m or fastmcp dev inspector).
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path when this package is loaded directly
# by fastmcp (i.e. not via `python -m`).
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastmcp import FastMCP  # noqa: E402

mcp = FastMCP(
    name="personal-workspace-agent",
    instructions=(
        "This server provides authenticated access to Google and GitHub on "
        "behalf of the workspace owner. Always call google_whoami or "
        "github_whoami first to confirm identity before making API calls."
    ),
)
