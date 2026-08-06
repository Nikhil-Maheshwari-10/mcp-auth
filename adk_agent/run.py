"""
Interactive CLI runner for the Personal Workspace Agent.

Starts a conversation loop where you type questions and the ADK agent responds,
calling MCP tools (google_whoami, github_whoami, etc.) as needed.

Run:
    python -m adk_agent.run
"""

import asyncio

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_agent.agent import create_agent

load_dotenv()

_APP_NAME = "personal-workspace-agent"
_USER_ID = "owner"


async def main() -> None:
    """Start the interactive agent conversation loop."""
    print("Initializing workspace agent (connecting to MCP server)...\n")

    agent = create_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=_APP_NAME,
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
    )

    print("✅ Workspace Agent ready.")
    print("   Try: 'who am I on Google?', 'what's my GitHub username?', 'quit'\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break

        message = types.Content(
            role="user",
            parts=[types.Part(text=user_input)],
        )

        print("Agent: ", end="", flush=True)
        async for event in runner.run_async(
            user_id=_USER_ID,
            session_id=session.id,
            new_message=message,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                print(event.content.parts[0].text)
        print()


if __name__ == "__main__":
    asyncio.run(main())
