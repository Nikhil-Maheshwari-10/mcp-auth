"""
ADK agent definition — wires the LlmAgent to the FastMCP server via MCPToolset.

The agent spawns mcp_server/server.py as a subprocess over stdio. ADK handles
the MCP protocol, discovers all registered tools, and makes them available to
the Gemini model automatically.

Requires GOOGLE_API_KEY in .env (get one at https://aistudio.google.com/app/apikey).
"""

from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool import StdioConnectionParams
from mcp import StdioServerParameters

from adk_agent.prompts import SYSTEM_PROMPT

load_dotenv()

# Absolute path to the project root — passed as cwd so the MCP server can find
# oauth/ packages and .tokens/ regardless of where the agent is launched from.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])


def create_agent() -> LlmAgent:
    """Construct and return the workspace LlmAgent with MCP tools attached.

    The MCPToolset launches mcp_server/server.py as a child process and
    communicates with it over stdio. ADK auto-discovers all @mcp.tool
    functions and makes them available to the Gemini model.
    """
    mcp_toolset = MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="python",
                args=["-m", "mcp_server.server"],
                cwd=_PROJECT_ROOT,
            )
        )
    )

    return LlmAgent(
        model="gemini-3.6-flash",
        name="workspace_agent",
        instruction=SYSTEM_PROMPT,
        tools=[mcp_toolset],
    )


# `adk web` discovers the agent via this module-level variable.
root_agent = create_agent()
