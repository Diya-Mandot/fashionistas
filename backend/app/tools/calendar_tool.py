from datetime import date, timedelta
from typing import Optional

from app.services.calendar_source import events_between
from app.tools.context import RunContext, ToolOutput


def read_calendar(ctx: RunContext, start_date: Optional[str] = None, end_date: Optional[str] = None) -> ToolOutput:
    """The user's real calendar (iCal feed) if configured, else the seeded demo calendar."""
    try:
        start = date.fromisoformat(start_date) if start_date else ctx.today
        end = date.fromisoformat(end_date) if end_date else start + timedelta(days=7)
    except ValueError:
        start, end = ctx.today, ctx.today + timedelta(days=7)
    cal = events_between(start, end, ctx.today)
    ctx.events_seen = cal.events
    names = ", ".join(e["name"] for e in cal.events[:4])
    detail = f"{cal.label} · {names}" if names else f"{cal.label} · nothing scheduled in that range"
    if cal.note:
        detail = f"{cal.note} · {detail}"
    result = {"events": cal.events, "count": len(cal.events), "calendar": cal.label}
    if cal.note:
        result["note"] = cal.note
    return ToolOutput(
        result=result,
        title=f"Read {cal.label.lower()}: {len(cal.events)} event{'s' if len(cal.events) != 1 else ''}",
        detail=detail,
        source="live" if cal.source == "ics" else "local",
        kind="fallback" if cal.note else "tool_call",
    )
