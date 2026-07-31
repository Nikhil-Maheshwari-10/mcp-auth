"""
Builds the Google authorization URL and exchanges the returned code for a token.

Entry point for the Google OAuth2 + PKCE flow:
  1. Generate PKCE verifier + challenge
  2. Build the authorization URL and open it in the browser
  3. Start the local callback listener and wait for the redirect
  4. Exchange the authorization code for access + refresh tokens
  5. Print the tokens (no storage yet — that's a later phase)

Run directly:
    python3 -m oauth.google.auth
"""

import json
import secrets
import webbrowser
from urllib.parse import urlencode

import requests

from oauth.common.pkce import generate_code_challenge, generate_code_verifier
from oauth.google import config
from oauth.google.callback import wait_for_callback
from oauth.google import token_store


# Scopes — profile + Gmail + Calendar read access.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def build_authorization_url(code_challenge: str, state: str) -> str:
    """Construct the Google authorization URL with PKCE and all required params."""
    params = {
        "client_id": config.CLIENT_ID,
        "redirect_uri": config.REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",   # request a refresh_token alongside the access_token
        "prompt": "consent",        # force consent screen so refresh_token is always returned
    }
    return f"{config.AUTH_ENDPOINT}?{urlencode(params)}"


def exchange_code_for_token(code: str, code_verifier: str) -> dict:
    """POST the authorization code + PKCE verifier to Google's token endpoint.

    Returns the full token response dict, which includes:
        access_token, refresh_token, expires_in, token_type, id_token
    """
    payload = {
        "client_id": config.CLIENT_ID,
        "client_secret": config.CLIENT_SECRET,
        "redirect_uri": config.REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
    }
    response = requests.post(config.TOKEN_ENDPOINT, data=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def run() -> None:
    """Execute the full Google OAuth2 + PKCE flow end-to-end.

    If a valid token already exists on disk, skips the browser flow entirely
    and returns the cached token. Runs the full flow only when no token is
    stored or the stored token cannot be refreshed.
    """
    # --- Check for existing valid token first ---
    existing = token_store.get_valid_token()
    if existing:
        print("\n✅ Google: using existing token (no login needed)\n")
        print(json.dumps(existing, indent=2))
        return

    # --- Step 1: PKCE ---
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)  # CSRF protection

    # --- Step 2: Build URL and open browser ---
    auth_url = build_authorization_url(code_challenge, state)
    print("\n[Google OAuth] Opening browser for authorization...")
    print(f"  URL: {auth_url}\n")
    webbrowser.open(auth_url)

    # --- Step 3: Wait for redirect ---
    port = int(config.REDIRECT_URI.split(":")[-1].split("/")[0])
    print(f"[Google OAuth] Waiting for callback on port {port}...")
    auth_code, returned_state = wait_for_callback(port=port)

    # Verify state to prevent CSRF
    if returned_state != state:
        raise RuntimeError(
            f"State mismatch — possible CSRF attack.\n"
            f"  Expected: {state}\n"
            f"  Got:      {returned_state}"
        )

    # --- Step 4: Exchange code for tokens ---
    print("[Google OAuth] Exchanging authorization code for tokens...")
    token_data = exchange_code_for_token(auth_code, code_verifier)

    # --- Step 5: Save to disk ---
    token_store.save_token(token_data)

    # --- Step 6: Print result ---
    print("\n✅ Google OAuth successful!\n")
    print(json.dumps(token_data, indent=2))


if __name__ == "__main__":
    run()

