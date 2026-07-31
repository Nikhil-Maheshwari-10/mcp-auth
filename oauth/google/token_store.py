"""
Saves, loads, and refreshes Google OAuth tokens on disk.

Token file: .tokens/google.json  (gitignored)

Lifecycle:
  1. After a successful auth flow → call save_token(token_data)
  2. On the next run → call get_valid_token()
       - If no file: returns None  (caller must run the full auth flow)
       - If file exists and token is fresh: returns token_data as-is
       - If file exists but token is expired: silently refreshes and returns
         the new token_data (also saves the refreshed copy to disk)
"""

import json
import time
from pathlib import Path

import requests

from oauth.google import config

# Anchor path to the project root (two dirs above this file).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOKEN_PATH = _PROJECT_ROOT / ".tokens" / "google.json"

# Refresh 60 seconds before actual expiry to avoid edge-case failures.
_EXPIRY_BUFFER_SECONDS = 60


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
    print(f"[token_store] Google token saved → {TOKEN_PATH}")


def load_token() -> dict | None:
    """Return the token dict from disk, or None if the file doesn't exist."""
    if not TOKEN_PATH.exists():
        return None
    return json.loads(TOKEN_PATH.read_text())


# ---------------------------------------------------------------------------
# Expiry check
# ---------------------------------------------------------------------------

def is_expired(token_data: dict) -> bool:
    """Return True if the access_token is expired (or about to be).

    Uses the `saved_at` timestamp written by save_token() plus the
    `expires_in` field from Google's token response.
    """
    saved_at: float = token_data.get("saved_at", 0)
    expires_in: int = token_data.get("expires_in", 3600)
    return time.time() > saved_at + expires_in - _EXPIRY_BUFFER_SECONDS


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

def refresh_access_token(token_data: dict) -> dict:
    """Use the stored refresh_token to get a new access_token from Google.

    The refresh_token itself never expires (unless revoked), so we keep it
    from the original token_data and merge it into the refreshed response.

    Returns the updated token_data dict (also persisted to disk).

    Raises:
        RuntimeError: If no refresh_token is present or Google rejects the request.
    """
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise RuntimeError(
            "No refresh_token in stored Google token. "
            "Delete .tokens/google.json and run the full auth flow again."
        )

    payload = {
        "client_id": config.CLIENT_ID,
        "client_secret": config.CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    response = requests.post(config.TOKEN_ENDPOINT, data=payload, timeout=10)
    response.raise_for_status()
    refreshed = response.json()

    # Google's refresh response omits refresh_token — carry it forward.
    refreshed.setdefault("refresh_token", refresh_token)

    save_token(refreshed)
    print("[token_store] Google access_token refreshed.")
    return refreshed


# ---------------------------------------------------------------------------
# Main entry point used by auth.py
# ---------------------------------------------------------------------------

def get_valid_token() -> dict | None:
    """Return a ready-to-use token dict, handling load + refresh automatically.

    Returns:
        dict  — with a fresh access_token, or
        None  — if no token is stored (full auth flow required).
    """
    token_data = load_token()
    if token_data is None:
        return None

    if is_expired(token_data):
        print("[token_store] Google access_token expired — refreshing...")
        token_data = refresh_access_token(token_data)

    return token_data
