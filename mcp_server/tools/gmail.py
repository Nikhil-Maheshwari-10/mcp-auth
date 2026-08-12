import httpx
from core.logger import logger
from core.messages import TOOL_GMAIL_ERROR, INTERNAL_ERROR
from mcp_server import mcp
from mcp_server.tools.common import require_token, check_and_mark_call, check_account_ambiguity


def _gmail_err(context: str, exc: Exception) -> str:
    """Log and return a user-friendly error string for Gmail failures."""
    if isinstance(exc, httpx.HTTPStatusError):
        msg = f"{context}: Google API returned {exc.response.status_code}"
        logger.error(f"[GMAIL] {msg} — {exc.response.text[:120]}")
    elif isinstance(exc, RuntimeError):
        msg = str(exc)
        logger.warning(f"[GMAIL] {context}: {msg}")
    else:
        msg = TOOL_GMAIL_ERROR.format(str(exc))
        logger.error(f"[GMAIL] Unexpected error in {context}: {exc}", exc_info=True)
    return msg


_GMAIL_READ_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

_GMAIL_WRITE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

_GMAIL_READ_SCOPE_MISSING_MSG = (
    "Gmail read access was not granted during Google sign-in. "
    "Go to Settings → Re-authorize Google, and ensure you CHECK the box for Gmail read access on Google's consent screen."
)

_GMAIL_WRITE_SCOPE_MISSING_MSG = (
    "Gmail send/write access was not granted during Google sign-in. "
    "Go to Settings → Re-authorize Google, and ensure you CHECK the box for Gmail send/compose permissions on Google's consent screen."
)


def _has_gmail_read_scope(token: dict) -> bool:
    """Return True if the token has at least one Gmail read scope."""
    granted = set((token.get("scope") or "").split())
    return any(s in granted for s in _GMAIL_READ_SCOPES)


def _has_gmail_write_scope(token: dict) -> bool:
    """Return True if the token has at least one Gmail write/send scope."""
    granted = set((token.get("scope") or "").split())
    return any(s in granted for s in _GMAIL_WRITE_SCOPES)


@mcp.tool
async def google_list_emails(max_results: int = 5, account_email: str = "", workspace_id: str = "", user_id: str = "") -> list[dict]:
    """List the most recent Gmail messages for the authenticated user.

    Args:
        max_results: Number of emails to return (default 5, max 20).
        account_email: The connected Gmail address to check (optional if single account).
        user_id: The UUID of the user whose emails to fetch (optional if set in context).

    Returns:
        A list of dicts, each with: id, subject, from, date, snippet.
    """
    ambiguity = await check_account_ambiguity(account_email, provider="google")
    if ambiguity:
        return [{"clarification_needed": ambiguity}]
    try:
        token = await require_token(workspace_id or user_id, "google", account_email=account_email)
        if not _has_gmail_read_scope(token):
            logger.warning(f"[GMAIL] Scope guard blocked google_list_emails for user {user_id}")
            return [{"error": _GMAIL_READ_SCOPE_MISSING_MSG}]

        max_results = min(max_results, 20)
        logger.info(f"Listing recent inbox emails (max_results: {max_results})")

        async with httpx.AsyncClient(timeout=10.0) as client:
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

        logger.success(f"Retrieved {len(results)} inbox emails from Gmail")
        return results
    except Exception as exc:
        err_msg = _gmail_err("google_list_emails", exc)
        return [{"error": err_msg}]


@mcp.tool
async def google_whoami(account_email: str = "", workspace_id: str = "", user_id: str = "") -> dict:
    """Fetch the authenticated Google user's profile to verify the token.

    Args:
        account_email: The connected Gmail address to check (optional if single account).
        user_id: The UUID of the user (optional if set in context).

    Returns:
        User's profile info (name, email, picture).
    """
    ambiguity = await check_account_ambiguity(account_email, provider="google")
    if ambiguity:
        return {"clarification_needed": ambiguity}
    try:
        token = await require_token(workspace_id or user_id, "google", account_email=account_email)
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {token['access_token']}"},
            )
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        err_msg = _gmail_err("google_whoami", exc)
        return {"error": err_msg}


@mcp.tool
async def gmail_send(to: str, subject: str, body: str, account_email: str = "", workspace_id: str = "", user_id: str = "") -> dict:
    """Send an email on behalf of the authenticated user."""
    import base64
    from email.message import EmailMessage

    if check_and_mark_call("gmail_send", {"to": to, "subject": subject, "account_email": account_email}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(workspace_id or user_id, "google", account_email=account_email)
        if not _has_gmail_write_scope(token):
            logger.warning(f"[GMAIL] Scope guard blocked gmail_send for user {user_id}")
            return {"error": _GMAIL_WRITE_SCOPE_MISSING_MSG}

        logger.info(f"Sending email to '{to}' with subject '{subject}'")

        msg = EmailMessage()
        msg.set_content(body)
        msg["To"] = to
        msg["Subject"] = subject

        raw_bytes = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                json={"raw": raw_bytes},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.success(f"Email sent successfully (msg_id: {data.get('id')})")
            return {
                "status": "sent",
                "id": data.get("id"),
                "threadId": data.get("threadId"),
                "to": to,
                "subject": subject,
            }
    except Exception as exc:
        err_msg = _gmail_err("gmail_send", exc)
        return {"error": err_msg}


@mcp.tool
async def gmail_reply(thread_id: str, to: str, subject: str, body: str, account_email: str = "", workspace_id: str = "", user_id: str = "") -> dict:
    """Reply to an existing email thread."""
    import base64
    from email.message import EmailMessage

    if check_and_mark_call("gmail_reply", {"thread_id": thread_id, "to": to, "account_email": account_email}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(workspace_id or user_id, "google", account_email=account_email)
        if not _has_gmail_write_scope(token):
            logger.warning(f"[GMAIL] Scope guard blocked gmail_reply for user {user_id}")
            return {"error": _GMAIL_WRITE_SCOPE_MISSING_MSG}

        logger.info(f"Replying to email thread '{thread_id}' (recipient: '{to}')")

        msg = EmailMessage()
        msg.set_content(body)
        msg["To"] = to
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"

        raw_bytes = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                json={"raw": raw_bytes, "threadId": thread_id},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.success(f"Reply sent successfully (msg_id: {data.get('id')})")
            return {
                "status": "replied",
                "id": data.get("id"),
                "threadId": data.get("threadId"),
                "to": to,
            }
    except Exception as exc:
        err_msg = _gmail_err("gmail_reply", exc)
        return {"error": err_msg}


@mcp.tool
async def gmail_archive(message_id: str, account_email: str = "", workspace_id: str = "", user_id: str = "") -> dict:
    """Archive a Gmail message by removing it from the INBOX."""
    if check_and_mark_call("gmail_archive", {"message_id": message_id, "account_email": account_email}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(workspace_id or user_id, "google", account_email=account_email)
        if not _has_gmail_write_scope(token):
            logger.warning(f"[GMAIL] Scope guard blocked gmail_archive for user {user_id}")
            return {"error": _GMAIL_WRITE_SCOPE_MISSING_MSG}

        logger.info(f"Archiving Gmail message '{message_id}'")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                json={"removeLabelIds": ["INBOX"]},
            )
            resp.raise_for_status()
            logger.success(f"Message '{message_id}' archived")
            return {
                "status": "archived",
                "id": message_id,
            }
    except Exception as exc:
        err_msg = _gmail_err("gmail_archive", exc)
        return {"error": err_msg}


def _decode_data(data_str: str) -> str:
    import base64
    try:
        return base64.urlsafe_b64decode(data_str).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_body_text(payload: dict) -> str:
    """Recursively extract plain text or readable content from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if mime_type == "text/plain" and body_data:
        return _decode_data(body_data)

    parts = payload.get("parts", [])
    text_parts = []
    html_parts = []

    for part in parts:
        part_mime = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data")
        if part_mime == "text/plain" and part_data:
            text_parts.append(_decode_data(part_data))
        elif part_mime == "text/html" and part_data:
            html_parts.append(_decode_data(part_data))
        elif "parts" in part:
            sub = _extract_body_text(part)
            if sub:
                text_parts.append(sub)

    if text_parts:
        return "\n".join(text_parts).strip()
    if html_parts:
        import re
        html = "\n".join(html_parts)
        text = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
        text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return " ".join(text.split()).strip()
    if body_data:
        return _decode_data(body_data)
    return ""


@mcp.tool
async def gmail_get_email(message_id: str, account_email: str = "", workspace_id: str = "", user_id: str = "") -> dict:
    """Read the full body content, headers, and details of a specific Gmail message."""
    try:
        token = await require_token(workspace_id or user_id, "google", account_email=account_email)
        if not _has_gmail_read_scope(token):
            logger.warning(f"[GMAIL] Scope guard blocked gmail_get_email for user {user_id}")
            return {"error": _GMAIL_READ_SCOPE_MISSING_MSG}

        logger.info(f"Reading full content for Gmail message '{message_id}'")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                params={"format": "full"},
            )
            resp.raise_for_status()
            data = resp.json()

            payload = data.get("payload", {})
            headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
            body_text = _extract_body_text(payload)

            subject = headers.get("Subject", "(no subject)")
            logger.success(f"Loaded full email content: '{subject}' ({len(body_text)} chars)")

            return {
                "id": data.get("id"),
                "threadId": data.get("threadId"),
                "subject": subject,
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "date": headers.get("Date", ""),
                "snippet": data.get("snippet", ""),
                "body": body_text or data.get("snippet", ""),
            }
    except Exception as exc:
        err_msg = _gmail_err("gmail_get_email", exc)
        return {"error": err_msg}


@mcp.tool
async def gmail_search_emails(
    query: str,
    max_results: int = 5,
    account_email: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> list[dict]:
    """Search for emails matching a Gmail search query."""
    ambiguity = await check_account_ambiguity(account_email, provider="google")
    if ambiguity:
        return [{"clarification_needed": ambiguity}]
    try:
        token = await require_token(workspace_id or user_id, "google", account_email=account_email)
        if not _has_gmail_read_scope(token):
            logger.warning(f"[GMAIL] Scope guard blocked gmail_search_emails for user {user_id}")
            return [{"error": _GMAIL_READ_SCOPE_MISSING_MSG}]

        max_results = min(max_results, 20)
        logger.info(f"Searching Gmail with query '{query}' (max_results: {max_results})")

        async with httpx.AsyncClient(timeout=15.0) as client:
            list_resp = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                params={"q": query, "maxResults": max_results},
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
                    "threadId": msg.get("threadId"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "from": headers.get("From", ""),
                    "date": headers.get("Date", ""),
                    "snippet": data.get("snippet", ""),
                })

        logger.success(f"Gmail search query '{query}' returned {len(results)} messages")
        return results
    except Exception as exc:
        err_msg = _gmail_err("gmail_search_emails", exc)
        return [{"error": err_msg}]


@mcp.tool
async def gmail_mark_as_read(message_id: str, account_email: str = "", workspace_id: str = "", user_id: str = "") -> dict:
    """Mark an unread Gmail message as read."""
    if check_and_mark_call("gmail_mark_as_read", {"message_id": message_id, "account_email": account_email}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(workspace_id or user_id, "google", account_email=account_email)
        if not _has_gmail_write_scope(token):
            logger.warning(f"[GMAIL] Scope guard blocked gmail_mark_as_read for user {user_id}")
            return {"error": _GMAIL_WRITE_SCOPE_MISSING_MSG}

        logger.info(f"Marking Gmail message '{message_id}' as read")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                json={"removeLabelIds": ["UNREAD"]},
            )
            resp.raise_for_status()
            logger.success(f"Message '{message_id}' marked as read")
            return {
                "status": "marked_as_read",
                "id": message_id,
            }
    except Exception as exc:
        err_msg = _gmail_err("gmail_mark_as_read", exc)
        return {"error": err_msg}



