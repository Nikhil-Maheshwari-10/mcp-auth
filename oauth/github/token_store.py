"""
Saves and loads GitHub OAuth tokens on disk.

Token file: .tokens/github.json  (gitignored)

GitHub OAuth App access tokens do not expire (unlike Google's), so there is
no refresh logic here. The token is valid until the user revokes it on
github.com/settings/applications.

Lifecycle:
  1. After a successful auth flow → call save_token(token_data)
  2. On the next run → call get_valid_token()
       - If no file: returns None  (caller must run the full auth flow)
       - If file exists: returns token_data as-is
"""

import json
import time
from pathlib import Path

# Anchor path to the project root (two dirs above this file).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOKEN_PATH = _PROJECT_ROOT / ".tokens" / "github.json"


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------

def save_token(token_data: dict) -> None:
    """Write *token_data* to TOKEN_PATH, adding a `saved_at` timestamp.

    Creates .tokens/ if it doesn't exist yet.
    """
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {**token_data, "saved_at": time.time()}
    TOKEN_PATH.write_text(json.dumps(payload, indent=2))
    print(f"[token_store] GitHub token saved → {TOKEN_PATH}")


def load_token() -> dict | None:
    """Return the token dict from disk, or None if the file doesn't exist."""
    if not TOKEN_PATH.exists():
        return None
    return json.loads(TOKEN_PATH.read_text())


# ---------------------------------------------------------------------------
# Main entry point used by auth.py
# ---------------------------------------------------------------------------

def get_valid_token() -> dict | None:
    """Return the stored token dict, or None if no token exists yet.

    GitHub tokens don't expire, so no refresh logic is needed. If the token
    ever stops working (user revoked it), delete .tokens/github.json and
    run the full auth flow again.

    Returns:
        dict  — with access_token ready to use, or
        None  — if no token is stored (full auth flow required).
    """
    token_data = load_token()
    if token_data is None:
        return None

    return token_data
