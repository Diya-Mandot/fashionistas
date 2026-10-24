from datetime import date, timedelta
from typing import Optional

from app.seed import events_between
from app.tools.context import RunContext, ToolOutput


def read_calendar(ctx: RunContext, start_date: Optional[str] = None, end_date: Optional[str] = None) -> ToolOutput:
    """Mock calendar served from seed.py (no OAuth). Dates are relative to today."""
    try:
        start = date.fromisoformat(start_date) if start_date else ctx.today
        end = date.fromisoformat(end_date) if end_date else start + timedelta(days=7)
    except ValueError:
        start, end = ctx.today, ctx.today + timedelta(days=7)
    events = events_between(start, end, ctx.today)
    ctx.events_seen = events
    names = ", ".join(e["name"] for e in events[:4])
    return ToolOutput(
        result={"events": events, "count": len(events)},
        title=f"Read calendar: {len(events)} event{'s' if len(events) != 1 else ''}",
        detail=f"Demo calendar · {names}" if names else "Demo calendar · nothing scheduled in that range",
        source="local",  # seeded demo calendar by design (no OAuth); not an API mock
    )
