"""
adk_agent — Google ADK agent that uses the FastMCP server as its tool source.

The agent connects to mcp_server/server.py via stdio, discovers the 4 tools
(google_get_token, google_whoami, github_get_token, github_whoami), and can
answer questions about the workspace owner's identity and credentials.

Entry point:
    python -m adk_agent.run
"""
