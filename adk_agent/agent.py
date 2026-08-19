"""
ADK agent definition — wires the LlmAgent directly to tool functions.

ARCHITECTURE NOTE — Why we bypass MCPToolset here
──────────────────────────────────────────────────
ADK's MCPToolset spawns the MCP server as a subprocess and communicates
via JSON-RPC over stdio.  Even though ADK does cache the MCP session
between requests, it still calls `session.list_tools()` on *every*
`/run_sse` invocation to re-discover tool schemas — a ~100-200 ms
JSON-RPC roundtrip that adds up.

Since our tools are plain Python async functions decorated with
`@mcp.tool` (which leaves the original function unchanged), we can
import them directly and register them as native ADK tools. This:

  • Eliminates the list_tools() roundtrip per request (~100-200 ms)
  • Eliminates JSON-RPC call_tool() serialisation overhead (~50-100 ms)
  • Keeps the DB connection pool warm (same process as ADK)
  • Leaves mcp_server/server.py untouched for Claude Desktop / stdio use

Requires GEMINI_API_KEYS in .env containing a comma-separated list of keys.
"""

import os
from typing import AsyncGenerator
from dotenv import load_dotenv
from pydantic import Field
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini, _ResourceExhaustedError
from google.genai.errors import ClientError
from core.logger import logger
from adk_agent.prompts import SYSTEM_PROMPT

# ── Tool imports — plain async functions from the framework-agnostic tools/ package ─
# tools/ has no FastMCP or ADK dependency. mcp_server/ wraps them for Claude Desktop.
from tools.gmail import (
    google_list_emails,
    google_whoami,
    gmail_get_email,
    gmail_search_emails,
    gmail_send,
    gmail_reply,
    gmail_archive,
    gmail_mark_as_read,
)
from tools.calendar import (
    google_list_calendar_events,
    calendar_search_events,
    calendar_get_event,
    calendar_create_event,
    calendar_update_event,
    calendar_delete_event,
)
from tools.github import (
    github_whoami,
    github_list_repos,
    github_list_issues,
    github_list_pull_requests,
    github_get_issue,
    github_get_pr,
    github_get_file_contents,
    github_get_repo_tree,
    github_create_issue,
    github_comment_on_issue,
    github_close_issue,
    github_create_pr,
    github_list_branches,
)

load_dotenv()


from google.adk.agents.readonly_context import ReadonlyContext


async def _get_connected_accounts(user_id_str: str, workspace_id_str: str | None = None) -> str:
    """Fetch all connected accounts for the user/workspace asynchronously."""
    import uuid
    from db.token_repo import get_all_provider_tokens

    try:
        uid = uuid.UUID(user_id_str.strip())
    except Exception:
        return "No active session."

    wid: uuid.UUID | None = None
    if workspace_id_str:
        try:
            wid = uuid.UUID(workspace_id_str.strip())
        except Exception:
            pass

    try:
        g_tokens = await get_all_provider_tokens(uid, "google", workspace_id=wid)
        gh_tokens = await get_all_provider_tokens(uid, "github", workspace_id=wid)
    except Exception as e:
        logger.error(f"Failed to fetch connected accounts for prompt: {e}")
        return "Unable to load connected accounts."

    lines = []
    if g_tokens:
        lines.append("Google (Gmail & Calendar):")
        for idx, t in enumerate(g_tokens, 1):
            email = t.get("provider_username") or "(unknown email)"
            lines.append(f"  {idx}. {email}")
    else:
        lines.append("Google (Gmail & Calendar): None connected")

    if gh_tokens:
        lines.append("GitHub:")
        for idx, t in enumerate(gh_tokens, 1):
            uname = t.get("provider_username") or "(unknown username)"
            lines.append(f"  {idx}. @{uname}")
    else:
        lines.append("GitHub: None connected")

    return "\n".join(lines)


async def _resolve_identity(target_id: str) -> tuple[str, str | None]:
    """
    Given an ADK session target_id (which may be a workspace_id or a user_id),
    return (real_user_id_str, workspace_id_str_or_None).

    In workspace mode, ADK uses workspace_id as ctx.user_id. We check WorkspaceUser
    to resolve the actual login user_id so token DB lookups work correctly.
    """
    import uuid
    try:
        tid = uuid.UUID(target_id.strip())
    except Exception:
        return target_id, None

    from db.workspace_repo import get_owner_user_id_for_workspace
    owner_uid = await get_owner_user_id_for_workspace(tid)
    if owner_uid is not None:
        # target_id is a workspace_id; resolve the real user_id
        return str(owner_uid), str(tid)

    # target_id is a plain user_id (single-account mode)
    return target_id, None


async def get_instruction(ctx: ReadonlyContext) -> str:
    target_id = ctx.user_id if ctx else ""
    if target_id:
        real_user_id, workspace_id = await _resolve_identity(target_id)
        from tools.common import set_context_user_id, set_context_workspace_id
        set_context_user_id(real_user_id)
        if workspace_id:
            set_context_workspace_id(workspace_id)
        else:
            set_context_workspace_id(real_user_id)  # single-account: both point to user_id
        accounts_context = await _get_connected_accounts(real_user_id, workspace_id)
        session_label = f"workspace_id='{workspace_id}'" if workspace_id else f"user_id='{real_user_id}'"
    else:
        accounts_context = "No session context."
        session_label = "unknown"

    import re
    # Count Google accounts: numbered lines like "  1. email@domain" (NOT starting with @)
    google_count = len(re.findall(r"^\s+\d+\.\s+(?!@)\S", accounts_context, re.MULTILINE))
    # Count GitHub accounts: numbered lines like "  1. @username" (starting with @)
    github_count = len(re.findall(r"^\s+\d+\.\s+@", accounts_context, re.MULTILINE))

    reminders = []
    if google_count > 1:
        reminders.append(
            f"[MULTI-ACCOUNT: GOOGLE]\n"
            f"There are {google_count} Google accounts connected.\n"
            "RULE: If the user's message does NOT specify which account (or 'all'/'both'), "
            "you MUST ask which Google account to use before calling any Gmail/Calendar tool."
        )
    if github_count > 1:
        reminders.append(
            f"[MULTI-ACCOUNT: GITHUB]\n"
            f"There are {github_count} GitHub accounts connected.\n"
            "RULE: If the user's message does NOT specify which GitHub account (or 'all'/'both'), "
            "you MUST ask which GitHub account to use before calling any GitHub tool. "
            "Pass the chosen username in the account_username parameter."
        )
    multi_account_reminder = ("\n" + "\n\n".join(reminders)) if reminders else ""

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"[SYSTEM CONTEXT]\n"
        f"Session identity: {session_label}\n"
        f"{multi_account_reminder}\n\n"
        f"[CONNECTED ACCOUNTS]\n"
        f"{accounts_context}"
    )



def _extract_request_summary(llm_request) -> tuple[str, str]:
    """Extracts the incoming user question or tool response from the LLM request."""
    if not hasattr(llm_request, "contents") or not llm_request.contents:
        return ("", "")

    last_content = llm_request.contents[-1]
    role = getattr(last_content, "role", "")
    parts = getattr(last_content, "parts", []) or []

    # If the latest content is a user prompt
    if role == "user":
        texts = []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                texts.append(text)
        if texts:
            return ("USER_QUESTION", " ".join(texts).strip())

    # If the latest content is a tool result
    for part in parts:
        fn_resp = getattr(part, "function_response", None)
        if fn_resp:
            fn_name = getattr(fn_resp, "name", "tool")
            return ("TOOL_RESPONSE", f"Received tool output for '{fn_name}'")

    # Fallback to the latest user message in history
    for content in reversed(llm_request.contents):
        if getattr(content, "role", "") == "user":
            texts = [getattr(p, "text", "") for p in getattr(content, "parts", []) if getattr(p, "text", None)]
            if texts:
                return ("USER_QUESTION", " ".join(texts).strip())

    return ("", "")


class RotatedGemini(Gemini):
    """A custom ADK Gemini model that:
    1. Logs user questions ([CHAT] Q: ...) and agent responses ([CHAT] A: ...)
    2. Implements API key rotation on quota exhaustion.
    """
    api_keys: list[str] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request, stream: bool = False
    ) -> AsyncGenerator:
        req_type, req_summary = _extract_request_summary(llm_request)
        if req_type == "USER_QUESTION":
            logger.info(f"[CHAT] Q: {req_summary}")
        elif req_type == "TOOL_RESPONSE":
            logger.debug(f"[AGENT] {req_summary}")

        last_err = None
        for attempt, key in enumerate(self.api_keys):
            try:
                # Clear cached properties to force client recreation with the new key
                if 'api_client' in self.__dict__:
                    del self.__dict__['api_client']
                if '_live_api_client' in self.__dict__:
                    del self.__dict__['_live_api_client']

                self.client_kwargs = {"api_key": key.strip()}

                collected_texts: list[str] = []
                tool_calls: list[str] = []

                async for res in super().generate_content_async(llm_request, stream):
                    if hasattr(res, "content") and res.content:
                        for part in getattr(res.content, "parts", []):
                            is_thought = getattr(part, "thought", False)
                            if not is_thought:
                                text = getattr(part, "text", None)
                                if text:
                                    if getattr(res, "partial", False):
                                        collected_texts.append(text)
                                    elif not stream:
                                        collected_texts.append(text)

                            fc = getattr(part, "function_call", None)
                            if fc and getattr(fc, "name", None):
                                fn_name = fc.name
                                args = getattr(fc, "args", {}) or {}
                                args_summary = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:2])
                                tool_calls.append(f"{fn_name}({args_summary})")

                    yield res

                # Stream complete: log answer preview or tool calls
                full_answer = "".join(collected_texts).strip()
                if full_answer:
                    preview = full_answer[:140] + ("..." if len(full_answer) > 140 else "")
                    logger.info(f"[CHAT] A: {preview}")
                elif tool_calls:
                    logger.info(f"[AGENT] Calling tool: {', '.join(tool_calls)}")

                return
            except (_ResourceExhaustedError, ClientError) as e:
                is_429 = getattr(e, 'code', None) == 429
                if not is_429 and not isinstance(e, _ResourceExhaustedError):
                    raise
                # Quota exhausted on this key, save error and try next
                logger.warning(
                    f"Quota exhausted on Gemini key {key[:6]}... switching to next key (Attempt {attempt+1}/{len(self.api_keys)})"
                )
                last_err = e

        # If we exhausted all keys, raise the last error
        if last_err:
            logger.error("All Gemini API keys in the pool have exhausted quota!")
            raise last_err



def create_agent() -> LlmAgent:
    """Construct and return the workspace LlmAgent with native tool functions.
    
    Uses RotatedGemini to automatically handle API quota exhaustion.
    """
    keys_str = os.getenv("GEMINI_API_KEYS", os.getenv("GOOGLE_API_KEY", ""))
    keys = [k.strip() for k in keys_str.strip('"\'').split(",") if k.strip()]
    
    if not keys:
        logger.warning("No GEMINI_API_KEYS found in environment!")
    else:
        logger.info(f"Loaded {len(keys)} Gemini API key(s) into rotation pool for model 'gemini-3.6-flash'")
        
    model = RotatedGemini(
        model="gemini-3.5-flash-lite",
        api_keys=keys
    )

    logger.success("Workspace ADK agent initialized with 25 native tools")
    return LlmAgent(
        model=model,
        name="workspace_agent",
        instruction=get_instruction,
        tools=[
            # Google Gmail tools
            google_whoami,
            google_list_emails,
            gmail_get_email,
            gmail_search_emails,
            gmail_send,
            gmail_reply,
            gmail_archive,
            gmail_mark_as_read,
            # Google Calendar tools
            google_list_calendar_events,
            calendar_search_events,
            calendar_get_event,
            calendar_create_event,
            calendar_update_event,
            calendar_delete_event,
            # GitHub tools
            github_whoami,
            github_list_repos,
            github_list_issues,
            github_list_pull_requests,
            github_get_issue,
            github_get_pr,
            github_get_file_contents,
            github_get_repo_tree,
            github_create_issue,
            github_comment_on_issue,
            github_close_issue,
            github_create_pr,
            github_list_branches,
        ],
    )


# `adk web` discovers the agent via this module-level variable.
# Created once at import time — Runner caches this across all requests.
root_agent = create_agent()
