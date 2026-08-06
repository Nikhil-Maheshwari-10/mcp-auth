"""
Loads GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI from environment.

Import this module at the top of google/auth.py. It reads the .env file (if
present) via python-dotenv and exposes three constants. Missing vars raise
immediately so you get a clear error before any network call is attempted.
"""

import os

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file).
load_dotenv()

def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: {name}\n"
            f"Copy .env.example → .env and fill in your Google credentials."
        )
    return value


CLIENT_ID: str = _require("GOOGLE_CLIENT_ID")
CLIENT_SECRET: str = _require("GOOGLE_CLIENT_SECRET")
REDIRECT_URI: str = _require("GOOGLE_REDIRECT_URI")

# Google's OAuth 2.0 endpoints — hardcoded, not env-configurable.
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

