from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter

from app.seed import calendar_events, events_between

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("")
def get_calendar(start: Optional[date] = None, end: Optional[date] = None) -> list[dict]:
    """Mock calendar (no OAuth). Events are dated relative to today."""
    if start is None and end is None:
        return calendar_events()
    start = start or date.today()
    end = end or start + timedelta(days=14)
    return events_between(start, end)
