"""
tools/ — Framework-agnostic tool functions for the Personal Workspace Agent.

These are plain Python async functions with no dependency on FastMCP, ADK, or
any other agent framework. They can be imported and used by any consumer:

  • adk_agent/agent.py  — imports directly for zero-overhead native ADK tools
  • mcp_server/server.py — wraps with @mcp.tool for Claude Desktop / MCP clients
"""
