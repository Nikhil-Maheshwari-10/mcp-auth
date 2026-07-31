"""
Loads GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GITHUB_REDIRECT_URI from environment.

Import this module at the top of github/auth.py. It reads the .env file (if
present) via python-dotenv and exposes three constants. Missing vars raise
immediately so you get a clear error before any network call is attempted.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: {name}\n"
            f"Copy .env.example → .env and fill in your GitHub credentials."
        )
    return value


CLIENT_ID: str = _require("GITHUB_CLIENT_ID")
CLIENT_SECRET: str = _require("GITHUB_CLIENT_SECRET")
REDIRECT_URI: str = _require("GITHUB_REDIRECT_URI")

# GitHub's OAuth 2.0 endpoints — hardcoded, not env-configurable.
AUTH_ENDPOINT = "https://github.com/login/oauth/authorize"
TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"

