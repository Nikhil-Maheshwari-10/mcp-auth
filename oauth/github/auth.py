"""
Builds the GitHub authorization URL and exchanges the returned code for a token.

Entry point for the GitHub OAuth2 + PKCE flow:
  1. Generate PKCE verifier + challenge
  2. Build the authorization URL and open it in the browser
  3. Start the local callback listener and wait for the redirect
  4. Exchange the authorization code for an access token
  5. Print the token (no storage yet — that's a later phase)

Key difference from Google:
  - GitHub returns tokens as application/x-www-form-urlencoded by default.
    We send Accept: application/json to get a JSON response instead.
  - No id_token or refresh_token in the default response (unless you request
    the refresh_token scope explicitly — not needed for this phase).

Run directly:
    python3 -m oauth.github.auth
"""

import json
import secrets
import webbrowser
from urllib.parse import urlencode

import requests

from oauth.common.pkce import generate_code_challenge, generate_code_verifier
from oauth.github import config
from oauth.github.callback import wait_for_callback
from oauth.github import token_store


# Scopes — profile + repos (incl. private) + notifications.
SCOPES = ["read:user", "user:email", "repo", "notifications"]


def build_authorization_url(code_challenge: str, state: str) -> str:
    """Construct the GitHub authorization URL with PKCE and all required params."""
    params = {
        "client_id": config.CLIENT_ID,
        "redirect_uri": config.REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{config.AUTH_ENDPOINT}?{urlencode(params)}"


def exchange_code_for_token(code: str, code_verifier: str) -> dict:
    """POST the authorization code + PKCE verifier to GitHub's token endpoint.

    Sends Accept: application/json so GitHub returns JSON instead of the
    default application/x-www-form-urlencoded format.

    Returns the full token response dict, which includes:
        access_token, token_type, scope
    """
    headers = {"Accept": "application/json"}
    payload = {
        "client_id": config.CLIENT_ID,
        "client_secret": config.CLIENT_SECRET,
        "redirect_uri": config.REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
    }
    response = requests.post(
        config.TOKEN_ENDPOINT, data=payload, headers=headers, timeout=10
    )
    response.raise_for_status()
    token_data = response.json()

    # GitHub surfaces OAuth errors in the JSON body with an "error" key.
    if "error" in token_data:
        raise RuntimeError(
            f"GitHub token exchange failed: {token_data['error']} — "
            f"{token_data.get('error_description', '')}"
        )

    return token_data


def run() -> None:
    """Execute the full GitHub OAuth2 + PKCE flow end-to-end.

    If a valid token already exists on disk, skips the browser flow entirely
    and returns the cached token. Runs the full flow only when no token is stored.
    """
    # --- Check for existing valid token first ---
    existing = token_store.get_valid_token()
    if existing:
        print("\n✅ GitHub: using existing token (no login needed)\n")
        print(json.dumps(existing, indent=2))
        return

    # --- Step 1: PKCE ---
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)  # CSRF protection

    # --- Step 2: Build URL and open browser ---
    auth_url = build_authorization_url(code_challenge, state)
    print("\n[GitHub OAuth] Opening browser for authorization...")
    print(f"  URL: {auth_url}\n")
    webbrowser.open(auth_url)

    # --- Step 3: Wait for redirect ---
    port = int(config.REDIRECT_URI.split(":")[-1].split("/")[0])
    print(f"[GitHub OAuth] Waiting for callback on port {port}...")
    auth_code, returned_state = wait_for_callback(port=port)

    # Verify state to prevent CSRF
    if returned_state != state:
        raise RuntimeError(
            f"State mismatch — possible CSRF attack.\n"
            f"  Expected: {state}\n"
            f"  Got:      {returned_state}"
        )

    # --- Step 4: Exchange code for token ---
    print("[GitHub OAuth] Exchanging authorization code for token...")
    token_data = exchange_code_for_token(auth_code, code_verifier)

    # --- Step 5: Save to disk ---
    token_store.save_token(token_data)

    # --- Step 6: Print result ---
    print("\n✅ GitHub OAuth successful!\n")
    print(json.dumps(token_data, indent=2))


if __name__ == "__main__":
    run()

