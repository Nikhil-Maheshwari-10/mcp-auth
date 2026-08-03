"""
adk_agent — Google ADK agent that uses the FastMCP server as its tool source.

Entry points:
    python -m adk_agent.run
    adk web adk_agent --port 8000
"""

from adk_agent.agent import root_agent, create_agent

__all__ = ["root_agent", "create_agent"]
