"""Daily outfit: five outfits for today, chosen for the day's weather and, if your Google Calendar
has something on today, its main occasion. Pick one and it's marked as worn.

Reuses the stylist agent's tools directly (no agent loop): get_weather_forecast for the day,
build_and_score_outfits for the rules shortlist + Claude scoring.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import get_settings
from app.core import outfit_generator as gen
from app.db import get_session
from app.models import AppFlag, WardrobeItem
from app.services.calendar_source import events_between
from app.tools.context import RunContext
from app.tools.outfits import build_and_score_outfits
from app.tools.weather import get_weather_forecast

router = APIRouter(prefix="/api/daily", tags=["daily"])

N_OUTFITS = 5
CACHE_TTL_S = 30 * 60
EVERYDAY = "everyday"

# Higher = dressier; the dressiest event of the day sets the outfit, since you can dress down
# a polished look for the rest of the day more easily than the reverse.
_HINT_RANK = {
    "formal": 5,
    "business casual": 4,
    "dressy-casual evening": 3,
    "smart casual": 2,
    "athletic": 1,
    "comfortable, travel-friendly": 1,
}

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
Day = date  # field below is named `date`; keep the type reachable under another name


class DailyRequest(BaseModel):
    date: Optional[Day] = None  # the browser's local date; defaults to the server's today
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    city: Optional[str] = Field(default=None, max_length=120)
    # A calendar event id from today's events, or "everyday" for no occasion. Omit to auto-pick.
    event_id: Optional[str] = Field(default=None, max_length=40)
    # Outfits already shown (lists of item ids) to skip, for "show me different ones".
    exclude: list[list[str]] = Field(default_factory=list, max_length=50)
    refresh: bool = False


class WearRequest(BaseModel):
    date: Optional[Day] = None
    item_ids: list[str] = Field(min_length=1, max_length=10)


def _rank(event: dict[str, Any]) -> int:
    return _HINT_RANK.get((event.get("dress_code_hint") or "").lower(), 0)


def main_occasion(events: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The dressiest event of the day; earliest wins a tie. None if the day is free."""
    if not events:
        return None
    return max(events, key=lambda e: (_rank(e), -events.index(e)))


def _everyday(day: date) -> dict[str, Any]:
    return {"id": EVERYDAY, "name": "Everyday", "date": day.isoformat(), "start_time": None,
            "location": "", "dress_code_hint": "casual everyday"}


def _flag_key(day: date) -> str:
    return f"daily_worn:{day.isoformat()}"


def _worn(session: Session, day: date) -> Optional[list[str]]:
    flag = session.get(AppFlag, _flag_key(day))
    if not flag or not flag.value:
        return None
    try:
        return json.loads(flag.value).get("item_ids") or None
    except ValueError:
        return None


def _closet_fingerprint(items: list[WardrobeItem]) -> str:
    raw = "|".join(sorted(f"{i.id}:{i.last_worn}:{i.number_of_times_worn}" for i in items))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@router.post("")
def daily_outfits(body: DailyRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    settings = get_settings()
    day = body.date or date.today()
    has_coords = body.lat is not None and body.lon is not None
    city = (body.city or "").strip() or (("your location" if has_coords else "") or settings.home_city)

    # Today's calendar. A broken calendar must never break the page: it just means no occasion.
    try:
        cal = events_between(day, day, day)
        events, cal_source, cal_label, cal_note = cal.events, cal.source, cal.label, cal.note
    except Exception as exc:
        events, cal_source, cal_label, cal_note = [], "none", "No calendar", f"Couldn't read your calendar ({type(exc).__name__})"

    if body.event_id == EVERYDAY:
        occasion = None
    elif body.event_id:
        occasion = next((e for e in events if e.get("id") == body.event_id), None) or main_occasion(events)
    else:
        occasion = main_occasion(events)

    closet = list(session.exec(select(WardrobeItem)))
    exclude = [frozenset(ids) for ids in body.exclude if ids]
    occasion_key = occasion["id"] if occasion else EVERYDAY
    cache_key = json.dumps(
        [day.isoformat(), city.lower(), round(body.lat or 0, 2), round(body.lon or 0, 2), occasion_key,
         occasion["name"] if occasion else "", sorted(sorted(x) for x in exclude), _closet_fingerprint(closet)]
    )
    hit = _cache.get(cache_key)
    if hit and not body.refresh and time.time() - hit[0] < CACHE_TTL_S:
        result = hit[1]
    else:
        result = _generate(day, city, body, occasion, closet, exclude)
        _cache[cache_key] = (time.time(), result)

    return {
        **result,
        "date": day.isoformat(),
        "calendar": {"source": cal_source, "label": cal_label, "note": cal_note},
        "events": events,
        "occasion": occasion,
        "worn_item_ids": _worn(session, day),
    }


def _generate(
    day: date,
    city: str,
    body: DailyRequest,
    occasion: Optional[dict[str, Any]],
    closet: list[WardrobeItem],
    exclude: list[frozenset[str]],
) -> dict[str, Any]:
    has_coords = body.lat is not None and body.lon is not None
    ctx = RunContext(
        run_id="daily",
        message="",
        today=day,
        home_city=city,
        emit=lambda _step: None,
        home_coords=(body.lat, body.lon) if has_coords else None,
    )
    wx = get_weather_forecast(ctx, city, day.isoformat(), day.isoformat())
    weather = next((d for d in wx.result.get("days", []) if d["date"] == day.isoformat()), None)
    weather_note = wx.result.get("note")
    if weather is None and wx.result.get("days"):
        weather, weather_note = None, f"No forecast for {day.isoformat()} yet."

    event = occasion or _everyday(day)
    vibe = (
        f"An outfit for {event['name']}" + (f" ({event['dress_code_hint']})" if event.get("dress_code_hint") else "")
        if occasion
        else "A comfortable, put-together everyday outfit for today"
    )
    scored = build_and_score_outfits(
        ctx,
        {"name": event["name"], "dress_code_hint": event.get("dress_code_hint"), "date": day.isoformat()},
        vibe=vibe,
        top_k=N_OUTFITS,
        exclude=exclude,
        distinct=True,
    )

    by_id = {i.id: i for i in closet}
    wctx = gen.WeatherContext(
        temp_f=scored.result.get("weather_used", {}).get("temp_f"),
        precipitation=bool(scored.result.get("weather_used", {}).get("precipitation")),
    )
    outfits = []
    for opt in scored.result.get("options", []):
        o = ctx.outfits[opt["outfit_ref"]]
        items = [by_id[i] for i in o.item_ids if i in by_id]
        cand = gen.Candidate(
            items=tuple(
                gen.ItemData(id=i.id, category=i.category, name=i.name, subcategory=i.subcategory, color=i.color,
                             style=i.style, season=i.season, last_worn=i.last_worn,
                             times_worn=i.number_of_times_worn, is_favorite=i.is_favorite)
                for i in items
            ),
            score=o.scores.get("overall", 0.0),
        )
        title, tip = gen.template_copy(cand, wctx, day)
        outfits.append(
            {"ref": o.ref, "item_ids": o.item_ids, "scores": o.scores, "title": title, "tip": tip, "rationale": o.hint}
        )

    _unique_titles(outfits, by_id)
    used = {i for o in outfits for i in o["item_ids"]}
    return {
        "city": wx.result.get("city", city),
        "weather": weather,
        "weather_note": weather_note,
        "weather_source": wx.source,
        "outfits": outfits,
        "items": [by_id[i].model_dump(mode="json") for i in used if i in by_id],
        "scored_by": scored.result.get("scored_by"),
        "candidates_scored": scored.result.get("candidates_scored", 0),
        "error": scored.result.get("error"),
    }


_HERO_ORDER = ("dresses", "tops", "activewear", "outerwear", "bottoms", "shoes", "bags", "accessories")


def _unique_titles(outfits: list[dict[str, Any]], by_id: dict[str, WardrobeItem]) -> None:
    """Several looks often share a style vibe ("Active Mode"); name those after their hero piece."""
    counts: dict[str, int] = {}
    for o in outfits:
        counts[o["title"]] = counts.get(o["title"], 0) + 1
    for o in outfits:
        if counts[o["title"]] < 2:
            continue
        items = [by_id[i] for i in o["item_ids"] if i in by_id]
        hero = min(items, key=lambda i: _HERO_ORDER.index(i.category) if i.category in _HERO_ORDER else 99, default=None)
        if hero:
            o["title"] = f"The {hero.name.strip()[:36]} Look"


@router.post("/wear")
def wear(body: WearRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Mark the chosen outfit as worn on `date`. Choosing again the same day replaces the earlier pick."""
    day = body.date or date.today()
    if day > date.today() + timedelta(days=1):
        raise HTTPException(400, "You can only wear an outfit today.")
    ids = list(dict.fromkeys(body.item_ids))
    items = [session.get(WardrobeItem, i) for i in ids]
    if any(i is None for i in items):
        raise HTTPException(404, "One of those items is no longer in your closet.")

    key = _flag_key(day)
    flag = session.get(AppFlag, key)
    if flag and flag.value:
        # Undo the earlier pick for today so wear counts stay honest.
        try:
            prev = json.loads(flag.value).get("prev", {})
        except ValueError:
            prev = {}
        for item_id, (last_worn, times) in prev.items():
            old = session.get(WardrobeItem, item_id)
            if old:
                old.last_worn = date.fromisoformat(last_worn) if last_worn else None
                old.number_of_times_worn = times
                session.add(old)
        session.flush()
        items = [session.get(WardrobeItem, i) for i in ids]

    prev_state = {i.id: [i.last_worn.isoformat() if i.last_worn else None, i.number_of_times_worn] for i in items}
    for i in items:
        i.number_of_times_worn += 1
        if i.last_worn is None or i.last_worn <= day:
            i.last_worn = day
        session.add(i)
    value = json.dumps({"item_ids": ids, "prev": prev_state})
    if flag:
        flag.value = value
    else:
        flag = AppFlag(key=key, value=value)
    session.add(flag)
    session.commit()
    return {"date": day.isoformat(), "worn_item_ids": ids, "items": [i.model_dump(mode="json") for i in items]}
