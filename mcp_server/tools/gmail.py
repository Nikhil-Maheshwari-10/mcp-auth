import httpx
from mcp_server import mcp
from mcp_server.tools.common import require_token


@mcp.tool
async def google_list_emails(max_results: int = 5, user_id: str = "") -> list[dict]:
    """List the most recent Gmail messages for the authenticated user.

    Args:
        max_results: Number of emails to return (default 5, max 20).
        user_id: The UUID of the user whose emails to fetch (optional if set in context).

    Returns:
        A list of dicts, each with: id, subject, from, date, snippet.
    """
    token = await require_token(user_id, "google")
    max_results = min(max_results, 20)

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step 1: list message IDs
        list_resp = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {token['access_token']}"},
            params={"maxResults": max_results, "labelIds": "INBOX"},
        )
        list_resp.raise_for_status()
        messages = list_resp.json().get("messages", [])

        results = []
        for msg in messages:
            detail = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
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
async def google_whoami(user_id: str = "") -> dict:
    """Fetch the authenticated Google user's profile to verify the token.

    Args:
        user_id: The UUID of the user (optional if set in context).

    Returns:
        User's profile info (name, email, picture).
    """
    token = await require_token(user_id, "google")
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )
        response.raise_for_status()
        return response.json()
