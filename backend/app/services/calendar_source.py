"""Calendar events for the agent: a real iCal feed (Google/Apple/Outlook "secret
address") when CALENDAR_ICS_URL is set, otherwise the seeded demo calendar.
Never fails: a broken feed falls back to the demo events with a note."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.seed import events_between as demo_events_between

CACHE_TTL_S = 5 * 60
_cache: dict[str, tuple[float, bytes]] = {}

_DRESS_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("wedding", "gala", "black tie", "opera"), "formal"),
    (("dinner", "date", "cocktail", "party", "theatre", "theater", "show"), "dressy-casual evening"),
    (("interview", "client", "pitch", "board", "presentation", "conference", "offsite", "first day"), "business casual"),
    (("run", "gym", "yoga", "workout", "hike", "tennis", "pilates", "climb"), "athletic"),
    (("brunch", "coffee", "lunch", "drinks"), "smart casual"),
    (("flight", "travel", "airport", "train"), "comfortable, travel-friendly"),
]


@dataclass
class CalendarResult:
    events: list[dict[str, Any]]
    source: str  # "ics" | "demo"
    label: str
    note: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


def calendar_configured() -> bool:
    return bool(get_settings().calendar_ics_url.strip())


def _include_demo() -> bool:
    flag = get_settings().calendar_include_demo
    return (not calendar_configured()) if flag is None else flag


def _fetch(url: str) -> bytes:
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < CACHE_TTL_S:
        return hit[1]
    if url.startswith("file://") or Path(url).expanduser().exists():
        data = Path(url.removeprefix("file://")).expanduser().read_bytes()
    else:
        res = httpx.get(url.replace("webcal://", "https://"), timeout=8.0, follow_redirects=True)
        res.raise_for_status()
        data = res.content
    _cache[url] = (time.time(), data)
    return data


def _hint(name: str, description: str) -> Optional[str]:
    m = re.search(r"dress(?:\s*code)?\s*[:\-]\s*([^\n.;]{2,60})", description, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    text = name.lower()
    for words, hint in _DRESS_HINTS:
        if any(w in text for w in words):
            return hint
    return None


def _ics_events(start: date, end: date) -> list[dict[str, Any]]:
    import icalendar
    import recurring_ical_events

    cal = icalendar.Calendar.from_ical(_fetch(get_settings().calendar_ics_url.strip()))
    raw = recurring_ical_events.of(cal).between(start, end + timedelta(days=1))
    events = []
    for ev in raw:
        dt = ev.get("DTSTART").dt if ev.get("DTSTART") else None
        if dt is None:
            continue
        if isinstance(dt, datetime):
            local = dt.astimezone() if dt.tzinfo else dt
            day, time_str = local.date(), local.strftime("%H:%M")
        else:
            day, time_str = dt, None
        if not (start <= day <= end):
            continue
        name = str(ev.get("SUMMARY") or "Busy").strip()
        desc = str(ev.get("DESCRIPTION") or "")
        events.append(
            {
                "date": day.isoformat(),
                "start_time": time_str,
                "name": name[:120],
                "location": str(ev.get("LOCATION") or "").strip()[:160],
                "dress_code_hint": _hint(name, desc),
                "calendar": "real",
            }
        )
    events.sort(key=lambda e: (e["date"], e["start_time"] or ""))
    for n, e in enumerate(events, 1):
        e["id"] = f"cal_{n:02d}"
    return events


def events_between(start: date, end: date, today: Optional[date] = None) -> CalendarResult:
    demo = [dict(e, calendar="demo") for e in demo_events_between(start, end, today)] if _include_demo() else []
    if not calendar_configured():
        return CalendarResult(events=demo_events_between(start, end, today), source="demo", label="Demo calendar")
    try:
        real = _ics_events(start, end)
        events = sorted(real + demo, key=lambda e: (e["date"], e.get("start_time") or ""))
        label = "Your calendar" + (" + demo trips" if demo else "")
        return CalendarResult(events=events, source="ics", label=label, extra={"real": len(real), "demo": len(demo)})
    except Exception as exc:
        fallback = demo_events_between(start, end, today)
        return CalendarResult(
            events=fallback, source="demo", label="Demo calendar",
            note=f"Couldn't read your calendar ({type(exc).__name__}); used the demo calendar",
        )
