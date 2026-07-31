import datetime
import requests
from mcp_server import mcp
from mcp_server.tools.common import require_token
from oauth.google import token_store

@mcp.tool
def google_list_calendar_events(max_results: int = 5) -> list[dict]:
    """List the next upcoming Google Calendar events for the authenticated user.

    Args:
        max_results: Number of events to return (default 5, max 20).

    Returns:
        A list of dicts, each with: summary, start, end, location, meet_link.

    Requires calendar.readonly scope — run `python -m oauth.google.auth` to re-auth
    if you haven't added this scope yet.
    """
    token = require_token(token_store)
    max_results = min(max_results, 20)
    now = datetime.datetime.utcnow().isoformat() + "Z"

    resp = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": f"Bearer {token['access_token']}"},
        params={
            "maxResults": max_results,
            "orderBy": "startTime",
            "singleEvents": True,
            "timeMin": now,
        },
        timeout=10,
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
