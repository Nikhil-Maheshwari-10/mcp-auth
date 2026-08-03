from datetime import datetime, timezone
import httpx
from mcp_server import mcp
from mcp_server.tools.common import require_token


@mcp.tool
async def google_list_calendar_events(max_results: int = 5, user_id: str = "") -> list[dict]:
    """List the next upcoming Google Calendar events for the authenticated user.

    Args:
        max_results: Number of events to return (default 5, max 20).
        user_id: The UUID of the user whose calendar to fetch (optional if set in context).

    Returns:
        A list of dicts, each with: summary, start, end, location, meet_link.
    """
    token = await require_token(user_id, "google")
    max_results = min(max_results, 20)
    now = datetime.now(tz=timezone.utc).isoformat()

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

    return results
