"""Demo closet (real photos) and mock calendar.

The closet comes from seed_images/photos/manifest.json: real product photos with
their attributes and wear history (add more with scripts/import_photos.py).
It deliberately has NO waterproof outerwear, so the rain gap triggers on rainy
trips. Calendar dates are computed relative to today so the demo always works.
"""

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import Session, delete, select

from app.models import AgentRunRecord, WardrobeItem

PHOTO_MANIFEST = Path(__file__).resolve().parent.parent / "seed_images" / "photos" / "manifest.json"
_PHOTO_FIELDS = ("name", "category", "subcategory", "color", "style", "formality", "season", "material", "brand", "waterproof", "is_favorite")


def _photo_manifest() -> list[dict[str, Any]]:
    try:
        return json.loads(PHOTO_MANIFEST.read_text()) if PHOTO_MANIFEST.exists() else []
    except (OSError, json.JSONDecodeError):
        return []


def closet_items(today: date | None = None) -> list[WardrobeItem]:
    today = today or date.today()
    items = []
    for n, entry in enumerate(_photo_manifest(), start=1):
        if not entry.get("category"):
            continue
        days = entry.get("days_since_worn")
        items.append(
            WardrobeItem(
                id=entry.get("id") or f"itm_photo{n:02d}",
                image_url=f"/media/seed/photos/{entry['file']}",
                last_worn=None if days is None else today - timedelta(days=int(days)),
                number_of_times_worn=int(entry.get("times_worn") or 0),
                source="seed",
                **{k: entry[k] for k in _PHOTO_FIELDS if entry.get(k) is not None},
            )
        )
    return items


# ---------------------------------------------------------------------------
# Mock calendar
# ---------------------------------------------------------------------------
def _next_weekday(today: date, weekday: int, *, include_today: bool = False) -> date:
    """Next date with the given weekday (Mon=0). Strictly after today unless include_today."""
    delta = (weekday - today.weekday()) % 7
    if delta == 0 and not include_today:
        delta = 7
    return today + timedelta(days=delta)


def calendar_events(today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    tue = _next_weekday(today, 1)
    wed, thu = tue + timedelta(days=1), tue + timedelta(days=2)
    sat = _next_weekday(today, 5, include_today=True)
    sun = sat + timedelta(days=1)
    mon = _next_weekday(today, 0)

    raw = [
        # Seattle tech conference trip
        (tue, "08:30", "Tech Conference Day 1", "Seattle Convention Center, Seattle", "business casual"),
        (tue, "19:30", "Team Dinner at Canlis", "Canlis, Seattle", "dressy, upscale restaurant"),
        (wed, "06:45", "Morning run", "Waterfront trail, Seattle", "athletic"),
        (wed, "09:00", "Tech Conference Day 2", "Seattle Convention Center, Seattle", "business casual"),
        (thu, "09:00", "Tech Conference Day 3 + flight home", "Seattle Convention Center, Seattle", "business casual, travel-friendly"),
        # NYC weekend
        (sat, "11:00", "Networking Brunch", "Balthazar, New York", "smart casual"),
        (sat, "19:00", "Broadway Show", "Majestic Theatre, New York", "evening, dressy-casual"),
        (sun, "10:00", "Gallery walk in Chelsea", "Chelsea, New York", "casual, lots of walking"),
        # New job
        (mon, "09:00", "First day at Northwind", "Northwind HQ (home city)", "business casual"),
    ]
    events = []
    for n, (day, time, name, location, dress) in enumerate(sorted(raw, key=lambda r: (r[0], r[1])), 1):
        events.append(
            {
                "id": f"evt_{n:02d}",
                "date": day.isoformat(),
                "start_time": time,
                "name": name,
                "location": location,
                "dress_code_hint": dress,
            }
        )
    return events


def events_between(start: date, end: date, today: date | None = None) -> list[dict[str, Any]]:
    return [e for e in calendar_events(today) if start.isoformat() <= e["date"] <= end.isoformat()]


# ---------------------------------------------------------------------------
# DB seeding
# ---------------------------------------------------------------------------
def seed_if_empty(session: Session) -> None:
    if session.exec(select(WardrobeItem).limit(1)).first() is None:
        session.add_all(closet_items())
        session.commit()


def reset(session: Session) -> int:
    """Restore the seed closet and clear runs. Returns the item count."""
    session.exec(delete(WardrobeItem))
    session.exec(delete(AgentRunRecord))
    items = closet_items()
    session.add_all(items)
    session.commit()
    return len(items)
