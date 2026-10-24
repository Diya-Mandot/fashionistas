"""find_closet_gaps: rules spot needs the closet can't meet; the Decisions API
rates each one's severity (must-have / nice-to-have)."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlmodel import Session, select

from app.db import engine
from app.integrations.decisions_client import GapIn, rate_gaps
from app.models import WardrobeItem
from app.tools.context import RunContext, ToolOutput

WARM = ("wool", "cashmere", "down", "fleece")


def _days_label(dates: list[str]) -> str:
    ds = sorted(date.fromisoformat(d) for d in dates)
    if len(ds) == 1:
        return ds[0].strftime("%a")
    return f"{ds[0].strftime('%a')}–{ds[-1].strftime('%a')}"


def find_closet_gaps(
    ctx: RunContext,
    events: Optional[list[dict[str, Any]]] = None,
    weather_days: Optional[list[dict[str, Any]]] = None,
) -> ToolOutput:
    events = events or ctx.events_seen
    days = weather_days or list(ctx.weather_by_date.values())
    with Session(engine) as session:
        closet = list(session.exec(select(WardrobeItem)))
    outer = [i for i in closet if i.category == "outerwear"]
    shoes = [i for i in closet if i.category == "shoes"]

    found: list[GapIn] = []
    rainy = [d for d in days if (d.get("precip_pct") or 0) >= 50]
    if rainy and not any(i.waterproof for i in outer):
        peak = max(d.get("precip_pct") or 0 for d in rainy)
        found.append(GapIn(need="waterproof outer layer", reason=f"{peak}% chance of rain {_days_label([d['date'] for d in rainy])}; no waterproof outerwear in closet"))
    if rainy and not any(i.waterproof for i in shoes):
        found.append(GapIn(need="water-resistant shoes", reason=f"Rain likely {_days_label([d['date'] for d in rainy])}; suede and mesh shoes soak through"))
    cold = [d for d in days if d.get("low_f") is not None and d["low_f"] < 38]
    if cold and not any(any(w in (i.material or "").lower() for w in WARM) and i.subcategory == "coat" for i in outer):
        found.append(GapIn(need="warm winter coat", reason=f"Lows of {min(d['low_f'] for d in cold)}°F"))
    texts = [f"{e.get('name', '')} {e.get('dress_code_hint', '')}".lower() for e in events]
    if any("black tie" in t or "gala" in t for t in texts) and not any(i.formality == "formal" and i.category == "dresses" for i in closet):
        found.append(GapIn(need="formal evening outfit", reason="Black-tie event on the calendar"))
    if any(w in t for t in texts for w in ("run", "gym", "workout")) and not any(i.category == "activewear" for i in closet):
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
        result={"gaps": gaps, "severity_rated_by": f"Decisions API ({rated.meta.source})"},
        title=f"Found gap{'s' if len(gaps) > 1 else ''}: {', '.join(g['need'] for g in gaps)}",
        detail=f"{top['need']} rated {top['severity']} · {top['reason']}" + (f" · {rated.meta.note}" if rated.meta.note else ""),
        source=rated.meta.source,
        kind="decision",
    )
