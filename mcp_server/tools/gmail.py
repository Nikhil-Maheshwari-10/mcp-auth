import requests
from mcp_server import mcp
from mcp_server.tools.common import require_token
from oauth.google import token_store

@mcp.tool
def google_list_emails(max_results: int = 5) -> list[dict]:
    """List the most recent Gmail messages for the authenticated user.

    Args:
        max_results: Number of emails to return (default 5, max 20).

    Returns:
        A list of dicts, each with: id, subject, from, date, snippet.

    Requires gmail.readonly scope — run `python -m oauth.google.auth` to re-auth
    if you haven't added this scope yet.
    """
    token = require_token(token_store)
    max_results = min(max_results, 20)

    # Step 1: list message IDs
    list_resp = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        headers={"Authorization": f"Bearer {token['access_token']}"},
        params={"maxResults": max_results, "labelIds": "INBOX"},
        timeout=10,
    )
    list_resp.raise_for_status()
    messages = list_resp.json().get("messages", [])

    results = []
    for msg in messages:
        detail = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
            headers={"Authorization": f"Bearer {token['access_token']}"},
            params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            timeout=10,
        )
        detail.raise_for_status()
        data = detail.json()
        headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        results.append({
            "id": msg["id"],
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": data.get("snippet", ""),
        })

    return results

@mcp.tool
def google_whoami() -> dict:
    """Fetch the authenticated Google user's profile to verify the token.

    Makes a GET request to Google's /userinfo endpoint using the stored
    access_token. Returns the user's name, email, and picture URL.

    Raises an error if not authenticated or if the token is invalid.
    """
    token = require_token(token_store)
    response = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {token['access_token']}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
