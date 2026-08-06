from datetime import datetime, timezone
import httpx
from core.logger import logger
from core.messages import TOOL_CALENDAR_ERROR, INTERNAL_ERROR
from mcp_server import mcp
from mcp_server.tools.common import require_token


def _calendar_err(context: str, exc: Exception) -> str:
    """Log and return a user-friendly error string for Calendar failures."""
    if isinstance(exc, httpx.HTTPStatusError):
        msg = f"{context}: Google Calendar API returned {exc.response.status_code}"
        logger.error(f"[CALENDAR] {msg} — {exc.response.text[:120]}")
    elif isinstance(exc, RuntimeError):
        msg = str(exc)
        logger.warning(f"[CALENDAR] {context}: {msg}")
    else:
        msg = TOOL_CALENDAR_ERROR.format(str(exc))
        logger.error(f"[CALENDAR] Unexpected error in {context}: {exc}", exc_info=True)
    return msg

_CALENDAR_SCOPES_REQUIRED = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

_CALENDAR_SCOPE_MISSING_MSG = (
    "Calendar access was not granted during Google sign-in. "
    "Go to Settings → Re-authorize Google to enable Calendar tools."
)


def _has_calendar_scope(token: dict) -> bool:
    """Return True if the token has all required Calendar scopes."""
    granted = set((token.get("scope") or "").split())
    return all(s in granted for s in _CALENDAR_SCOPES_REQUIRED)


@mcp.tool
async def google_list_calendar_events(max_results: int = 5, user_id: str = "") -> list[dict]:
    """List the next upcoming Google Calendar events for the authenticated user."""
    try:
        token = await require_token(user_id, "google")
        if not _has_calendar_scope(token):
            logger.warning(f"[CALENDAR] Scope guard blocked google_list_calendar_events for user {user_id}")
            return [{"error": _CALENDAR_SCOPE_MISSING_MSG}]
        max_results = min(max_results, 20)
        now = datetime.now(tz=timezone.utc).isoformat()
        logger.info(f"Listing upcoming calendar events (max_results: {max_results})")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                params={
                    "maxResults": max_results,
                    "orderBy": "startTime",
                    "singleEvents": True,
                    "timeMin": now,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])

        results = []
        for item in items:
            start = item.get("start", {})
            end = item.get("end", {})
            meet_link = None
            for ep in item.get("conferenceData", {}).get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri")
            results.append({
                "summary": item.get("summary", "(no title)"),
                "start": start.get("dateTime", start.get("date", "")),
                "end": end.get("dateTime", end.get("date", "")),
                "location": item.get("location", ""),
                "meet_link": meet_link,
            })

        logger.success(f"Retrieved {len(results)} upcoming calendar events")
        return results
    except Exception as exc:
        err_msg = _calendar_err("google_list_calendar_events", exc)
        return [{"error": err_msg}]


@mcp.tool
async def calendar_create_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: list[str] = None,
    user_id: str = "",
) -> dict:
    """Create a new event in the user's primary Google Calendar."""
    try:
        token = await require_token(user_id, "google")
        if not _has_calendar_scope(token):
            logger.warning(f"[CALENDAR] Scope guard blocked calendar_create_event for user {user_id}")
            return {"error": _CALENDAR_SCOPE_MISSING_MSG}
        logger.info(f"Creating calendar event '{summary}' from {start_time} to {end_time}")

        event_body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time} if "T" in start_time else {"date": start_time},
            "end": {"dateTime": end_time} if "T" in end_time else {"date": end_time},
        }

        if attendees:
            event_body["attendees"] = [{"email": a.strip()} for a in attendees if a.strip()]

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                json=event_body,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.success(f"Calendar event '{summary}' created (event_id: {data.get('id')})")
            return {
                "status": "created",
                "id": data.get("id"),
                "summary": data.get("summary"),
                "start": data.get("start"),
                "end": data.get("end"),
                "htmlLink": data.get("htmlLink"),
            }
    except Exception as exc:
        err_msg = _calendar_err("calendar_create_event", exc)
        return {"error": err_msg}


@mcp.tool
async def calendar_update_event(
    event_id: str,
    summary: str = None,
    start_time: str = None,
    end_time: str = None,
    description: str = None,
    location: str = None,
    user_id: str = "",
) -> dict:
    """Update an existing event in the user's primary Google Calendar."""
    try:
        token = await require_token(user_id, "google")
        if not _has_calendar_scope(token):
            logger.warning(f"[CALENDAR] Scope guard blocked calendar_update_event for user {user_id}")
            return {"error": _CALENDAR_SCOPE_MISSING_MSG}
        logger.info(f"Updating calendar event '{event_id}'")

        patch_body = {}
        if summary is not None:
            patch_body["summary"] = summary
        if description is not None:
            patch_body["description"] = description
        if location is not None:
            patch_body["location"] = location
        if start_time is not None:
            patch_body["start"] = {"dateTime": start_time} if "T" in start_time else {"date": start_time}
        if end_time is not None:
            patch_body["end"] = {"dateTime": end_time} if "T" in end_time else {"date": end_time}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.patch(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                json=patch_body,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.success(f"Calendar event '{event_id}' updated successfully")
            return {
                "status": "updated",
                "id": data.get("id"),
                "summary": data.get("summary"),
                "start": data.get("start"),
                "end": data.get("end"),
            }
    except Exception as exc:
        err_msg = _calendar_err("calendar_update_event", exc)
        return {"error": err_msg}


@mcp.tool
async def calendar_delete_event(event_id: str, user_id: str = "") -> dict:
    """Delete an event from the user's primary Google Calendar."""
    try:
        token = await require_token(user_id, "google")
        if not _has_calendar_scope(token):
            logger.warning(f"[CALENDAR] Scope guard blocked calendar_delete_event for user {user_id}")
            return {"error": _CALENDAR_SCOPE_MISSING_MSG}
        logger.info(f"Deleting calendar event '{event_id}'")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                headers={"Authorization": f"Bearer {token['access_token']}"},
            )
            resp.raise_for_status()
            logger.success(f"Calendar event '{event_id}' deleted")
            return {
                "status": "deleted",
                "id": event_id,
            }
    except Exception as exc:
        err_msg = _calendar_err("calendar_delete_event", exc)
        return {"error": err_msg}


@mcp.tool
async def calendar_search_events(
    query: str = "",
    time_min: str = None,
    time_max: str = None,
    max_results: int = 10,
    user_id: str = "",
) -> list[dict]:
    """Search for calendar events by text query or within a specific time window."""
    try:
        token = await require_token(user_id, "google")
        if not _has_calendar_scope(token):
            logger.warning(f"[CALENDAR] Scope guard blocked calendar_search_events for user {user_id}")
            return [{"error": _CALENDAR_SCOPE_MISSING_MSG}]
        max_results = min(max_results, 30)
        logger.info(f"Searching calendar events (query: '{query}', time_min: {time_min}, time_max: {time_max})")

        params = {
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if query:
            params["q"] = query
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers={"Authorization": f"Bearer {token['access_token']}"},
                params=params,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])

        results = []
        for item in items:
            start = item.get("start", {})
            end = item.get("end", {})
            meet_link = None
            for ep in item.get("conferenceData", {}).get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri")
            results.append({
                "id": item.get("id"),
                "summary": item.get("summary", "(no title)"),
                "start": start.get("dateTime", start.get("date", "")),
                "end": end.get("dateTime", end.get("date", "")),
                "location": item.get("location", ""),
                "description": item.get("description", ""),
                "meet_link": meet_link,
            })

        logger.success(f"Calendar search returned {len(results)} events")
        return results
    except Exception as exc:
        err_msg = _calendar_err("calendar_search_events", exc)
        return [{"error": err_msg}]


@mcp.tool
async def calendar_get_event(event_id: str, user_id: str = "") -> dict:
    """Retrieve full details for a specific calendar event."""
    try:
        token = await require_token(user_id, "google")
        if not _has_calendar_scope(token):
            logger.warning(f"[CALENDAR] Scope guard blocked calendar_get_event for user {user_id}")
            return {"error": _CALENDAR_SCOPE_MISSING_MSG}
        logger.info(f"Fetching calendar event '{event_id}'")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                headers={"Authorization": f"Bearer {token['access_token']}"},
            )
            resp.raise_for_status()
            item = resp.json()

        start = item.get("start", {})
        end = item.get("end", {})
        meet_link = None
        for ep in item.get("conferenceData", {}).get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                meet_link = ep.get("uri")

        attendees = [
            {"email": a.get("email"), "response_status": a.get("responseStatus")}
            for a in item.get("attendees", [])
        ]

        summary = item.get("summary", "(no title)")
        logger.success(f"Loaded calendar event: '{summary}'")

        return {
            "id": item.get("id"),
            "summary": summary,
            "description": item.get("description", ""),
            "start": start.get("dateTime", start.get("date", "")),
            "end": end.get("dateTime", end.get("date", "")),
            "location": item.get("location", ""),
            "attendees": attendees,
            "meet_link": meet_link,
            "htmlLink": item.get("htmlLink"),
            "status": item.get("status"),
        }
    except Exception as exc:
        err_msg = _calendar_err("calendar_get_event", exc)
        return {"error": err_msg}


