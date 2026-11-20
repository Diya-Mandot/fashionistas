"""Demo closet (real photos).

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

from app.config import get_settings
from app.models import AgentRunRecord, AppFlag, BuyCheck, WardrobeItem

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
# Date helpers
# ---------------------------------------------------------------------------
def _next_weekday(today: date, weekday: int, *, include_today: bool = False) -> date:
    """Next date with the given weekday (Mon=0). Strictly after today unless include_today."""
    delta = (weekday - today.weekday()) % 7
    if delta == 0 and not include_today:
        delta = 7
    return today + timedelta(days=delta)


# ---------------------------------------------------------------------------
# DB seeding
# ---------------------------------------------------------------------------
def seed_if_empty(session: Session) -> None:
    if session.exec(select(WardrobeItem).limit(1)).first() is None:
        session.add_all(closet_items())
        session.commit()


def reset(session: Session) -> int:
    """Restore the seed closet; clear runs, buy checks and the mock Pro flag. Returns the item count."""
    session.exec(delete(WardrobeItem))
    session.exec(delete(AgentRunRecord))
    session.exec(delete(BuyCheck))
    session.exec(delete(AppFlag))
    pending = Path(get_settings().uploads_dir) / "pending"
    for photo in pending.glob("chk_*") if pending.is_dir() else ():
        photo.unlink(missing_ok=True)
    items = closet_items()
    session.add_all(items)
    session.commit()
    return len(items)
