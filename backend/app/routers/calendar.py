from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter

from app.services.calendar_source import events_between

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("")
def get_calendar(start: Optional[date] = None, end: Optional[date] = None) -> dict:
    """Your real calendar (CALENDAR_ICS_URL) or the demo calendar, for a date range."""
    start = start or date.today()
    end = end or start + timedelta(days=14)
    cal = events_between(start, end)
    return {"source": cal.source, "label": cal.label, "note": cal.note, "events": cal.events}
