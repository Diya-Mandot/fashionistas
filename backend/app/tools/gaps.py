"""find_closet_gaps: rules spot needs the closet can't meet; Claude
rates each one's severity (must-have / nice-to-have)."""

from __future__ import annotations

import re

from datetime import date
from typing import Any, Optional

from sqlmodel import Session, select

from app.db import engine
from app.integrations.decisions_client import GapIn, rate_gaps
from app.models import WardrobeItem
from app.text_rules import is_athletic
from app.tools.context import RunContext, ToolOutput

WARM = ("wool", "cashmere", "down", "fleece")


def _days_label(dates: list[str]) -> str:
    ds = sorted(date.fromisoformat(d) for d in dates)
    if len(ds) == 1:
        return ds[0].strftime("%a")
    return f"{ds[0].strftime('%a')}–{ds[-1].strftime('%a')}"


OUTDOOR = re.compile(r"\b(hike|hiking|trail|trek|backpack\w*|camp\w*|mountain|mt\.?|peak|summit|ski\w*|snowboard\w*|snowshoe\w*|climb\w*|outdoor\w*)\b", re.I)
INSULATED = ("down", "fleece", "insulated", "puffer", "primaloft", "synthetic fill")


def _text(i: WardrobeItem) -> str:
    return f"{i.name} {i.subcategory} {i.material or ''}".lower()


def _days_for(events: list[dict[str, Any]], agent_days: list[dict[str, Any]], ctx: RunContext) -> list[dict[str, Any]]:
    """Prefer the forecast the weather tool actually fetched over the agent's paraphrase of it."""
    dates = {e.get("date") for e in events if e.get("date")} | {d.get("date") for d in agent_days if d.get("date")}
    real = [ctx.weather_by_date[d] for d in sorted(dates) if d in ctx.weather_by_date]
    return real or agent_days or list(ctx.weather_by_date.values())


def _is_snowy(d: dict[str, Any]) -> bool:
    return bool(d.get("snow")) or "snow" in str(d.get("summary", "")).lower()


def find_closet_gaps(
    ctx: RunContext,
    events: Optional[list[dict[str, Any]]] = None,
    weather_days: Optional[list[dict[str, Any]]] = None,
) -> ToolOutput:
    events = events or ctx.events_seen
    days = _days_for(events, weather_days or [], ctx)
    with Session(engine) as session:
        closet = list(session.exec(select(WardrobeItem)))
    outer = [i for i in closet if i.category == "outerwear"]
    shoes = [i for i in closet if i.category == "shoes"]
    accessories = [i for i in closet if i.category == "accessories"]

    texts = [f"{e.get('name', '')} {e.get('dress_code_hint', '')}".lower() for e in events]
    outdoor = any(OUTDOOR.search(t) for t in texts)
    snowy = [d for d in days if _is_snowy(d)]
    rainy = [d for d in days if (d.get("precip_pct") or 0) >= 50 and not _is_snowy(d)]
    wet = sorted(rainy + snowy, key=lambda d: d["date"])
    cold = [d for d in days if d.get("low_f") is not None and d["low_f"] < 38]
    freezing = [d for d in days if d.get("low_f") is not None and d["low_f"] <= 32]
    wintry = outdoor and (snowy or freezing)

    def wet_note(ds: list[dict[str, Any]]) -> str:
        kind = "snow" if any(_is_snowy(d) for d in ds) else "rain likely"
        return f"{kind} {_days_label([d['date'] for d in ds])}"

    found: list[GapIn] = []
    if not shoes:
        rain_note = f"; {wet_note(wet)}, so choose water-resistant ones" if wet else ""
        found.append(GapIn(need="shoes", reason=f"No shoes in the closet, so every outfit is missing footwear{rain_note}"))
    if wet and not any(i.waterproof for i in outer):
        peak = max(d.get("precip_pct") or 0 for d in wet)
        found.append(GapIn(need="waterproof outer layer", reason=f"{peak}% chance of precipitation, {wet_note(wet)}; no waterproof outerwear in closet"))
    if shoes and (wet or wintry) and not any(i.waterproof for i in shoes):
        if outdoor:
            why = wet_note(wet) if wet else f"lows of {min(d['low_f'] for d in freezing)}°F"
            found.append(GapIn(need="waterproof hiking boots", reason=f"Trail with {why}; none of your shoes are waterproof, so feet get wet and cold"))
        else:
            found.append(GapIn(need="water-resistant shoes", reason=f"{wet_note(wet).capitalize()}; suede and mesh shoes soak through"))
    if outdoor and cold:
        # A dress overcoat or blazer doesn't count on a trail: it needs a packable insulating layer.
        layers = [i for i in closet if i.category in ("outerwear", "activewear", "tops") and i.subcategory not in ("coat", "blazer")]
        if not any(any(w in _text(i) for w in INSULATED) for i in layers):
            found.append(GapIn(need="insulated hiking jacket", reason=f"Lows of {min(d['low_f'] for d in cold)}°F outdoors; no down, fleece or insulated layer that works on a trail"))
    elif cold and not any(any(w in (i.material or "").lower() for w in WARM) and i.subcategory == "coat" for i in outer):
        found.append(GapIn(need="warm winter coat", reason=f"Lows of {min(d['low_f'] for d in cold)}°F"))
    if wintry:
        low = min((d["low_f"] for d in days if d.get("low_f") is not None), default=None)
        temp = f"lows of {low}°F" if low is not None else "freezing temperatures"
        conditions = f"{wet_note(snowy)}, {temp}" if snowy else temp
        if not any(i.subcategory == "hat" and any(w in _text(i) for w in (*WARM, "beanie", "knit", "toque")) for i in accessories):
            found.append(GapIn(need="warm beanie", reason=f"Outdoors with {conditions}; a cotton cap won't keep your head warm"))
        if not any(any(w in _text(i) for w in ("glove", "mitten", "mitt")) for i in accessories):
            found.append(GapIn(need="insulated gloves", reason=f"Outdoors with {conditions}; no gloves in the closet"))
        if not any(any(w in _text(i) for w in ("thermal", "base layer", "baselayer", "merino")) for i in closet):
            found.append(GapIn(need="thermal base layer", reason=f"Outdoors with {conditions}; cotton next to skin stays wet and cold"))
    if any("black tie" in t or "gala" in t for t in texts) and not any(i.formality == "formal" and i.category == "dresses" for i in closet):
        found.append(GapIn(need="formal evening outfit", reason="Black-tie event on the calendar"))
    if any(is_athletic(t) for t in texts) and not any(i.category == "activewear" for i in closet):
        found.append(GapIn(need="workout clothes", reason="Workout on the calendar"))

    if not found:
        return ToolOutput(result={"gaps": []}, title="No closet gaps found", detail="The closet covers every event and the forecast")

    context = {"city": ctx.city, "events": [e.get("name") for e in events], "weather": days}
    rated = rate_gaps(found, context)
    ctx.note_source("decisions", rated.meta.source)
    gaps = [
        {"need": g.need, "reason": g.reason, "severity": r.severity, "p_must_have": r.probability_must_have}
        for g, r in zip(found, rated.ratings)
    ]
    ctx.gaps = gaps
    top = gaps[0]
    return ToolOutput(
        result={"gaps": gaps, "severity_rated_by": f"Claude ({rated.meta.source})"},
        title=f"Found gap{'s' if len(gaps) > 1 else ''}: {', '.join(g['need'] for g in gaps)}",
        detail=f"{top['need']} rated {top['severity']} · {top['reason']}" + (f" · {rated.meta.note}" if rated.meta.note else ""),
        source=rated.meta.source,
        kind="decision",
    )
