"""Calendar events for the agent, from (in order of preference) a connected Google Calendar
(OAuth, see google_calendar.py) or a real iCal feed (CALENDAR_ICS_URL). Never fails: with no
calendar connected, or if every source breaks, it returns no events (with a note on failure)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from app.config import get_settings
from app.services import google_calendar
from app.text_rules import has_word

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
    source: str  # "google" | "ics" | "none"
    label: str
    note: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


def ics_configured() -> bool:
    return bool(get_settings().calendar_ics_url.strip())


def calendar_configured() -> bool:
    return google_calendar.connected() or ics_configured()


def describe() -> str:
    """Short human label for the health badge."""
    if google_calendar.connected():
        email = (google_calendar.load_token() or {}).get("email")
        return f"Google Calendar ({email})" if email else "Google Calendar"
    return "your calendar (iCal)" if ics_configured() else "no calendar connected"


def _fetch(url: str, force: bool = False) -> bytes:
    hit = _cache.get(url)
    if hit and not force and time.time() - hit[0] < CACHE_TTL_S:
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
    for words, hint in _DRESS_HINTS:
        if has_word(name, words):
            return hint
    return None


def _sources() -> list[str]:
    """CALENDAR_ICS_URL may be a URL, an .ics file, a folder of .ics files, or several, comma-separated."""
    out: list[str] = []
    for part in (p.strip() for p in get_settings().calendar_ics_url.split(",")):
        if not part:
            continue
        path = Path(part.removeprefix("file://")).expanduser()
        if path.is_dir():
            out.extend(str(f) for f in sorted(path.glob("*.ics")))
        else:
            out.append(part)
    return out


def _ics_raw(start: date, end: date, force: bool = False) -> list[dict[str, Any]]:
    import icalendar
    import recurring_ical_events

    raw = []
    for src in _sources():
        cal = icalendar.Calendar.from_ical(_fetch(src, force))
        raw.extend(recurring_ical_events.of(cal).between(start, end + timedelta(days=1)))
    out = []
    for ev in raw:
        dt = ev.get("DTSTART").dt if ev.get("DTSTART") else None
        if dt is None:
            continue
        if isinstance(dt, datetime):
            local = dt.astimezone() if dt.tzinfo else dt
            day, time_str = local.date(), local.strftime("%H:%M")
        else:
            day, time_str = dt, None
        out.append(
            {
                "date": day,
                "start_time": time_str,
                "name": str(ev.get("SUMMARY") or "Busy"),
                "location": str(ev.get("LOCATION") or ""),
                "description": str(ev.get("DESCRIPTION") or ""),
            }
        )
    return out


def _finish(raw: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    """Shared shape for every real source: what the agent and the home page see."""
    events = []
    for ev in raw:
        if not (start <= ev["date"] <= end):
            continue
        name = ev["name"].strip() or "Busy"
        events.append(
            {
                "date": ev["date"].isoformat(),
                "start_time": ev["start_time"],
                "name": name[:120],
                "location": ev["location"].strip()[:160],
                "dress_code_hint": _hint(name, ev["description"]),
                "calendar": "real",
            }
        )
    return events


def events_between(start: date, end: date, today: Optional[date] = None, refresh: bool = False) -> CalendarResult:
    readers: list[tuple[str, str, Callable[[], list[dict[str, Any]]]]] = []
    if google_calendar.connected():
        readers.append(("google", "Google Calendar", lambda: google_calendar.fetch_events(start, end, force=refresh)))
    if ics_configured():
        readers.append(("ics", "calendar feed", lambda: _ics_raw(start, end, force=refresh)))
    if not readers:
        return CalendarResult(events=[], source="none", label="No calendar connected")

    real: list[dict[str, Any]] = []
    ok: list[str] = []
    notes: list[str] = []
    for key, name, read in readers:
        try:
            real.extend(_finish(read(), start, end))
            ok.append(key)
        except google_calendar.NotConnected as exc:
            notes.append(str(exc))
        except Exception as exc:
            notes.append(f"Couldn't read your {name} ({type(exc).__name__})")

    if not ok:
        return CalendarResult(events=[], source="none", label="No calendar", note="; ".join(notes))

    real.sort(key=lambda e: (e["date"], e["start_time"] or ""))
    for n, e in enumerate(real, 1):
        e["id"] = f"cal_{n:02d}"
    label = "Your Google Calendar" if ok == ["google"] else "Your calendar"
    return CalendarResult(
        events=real,
        source="google" if "google" in ok else "ics",
        label=label,
        note="; ".join(notes) or None,
        extra={"real": len(real)},
    )
