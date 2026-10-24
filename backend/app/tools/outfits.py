"""build_and_score_outfits: the ported rules generator narrows the closet to ≤18
sensible combos, then the Decisions API scores each one on five criteria.

Candidates go to Decisions by index only; results come back to the agent as
outfit refs ("E2-A"). Item IDs never leave the server.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from sqlmodel import Session, select

from app.core import outfit_generator as gen
from app.db import engine
from app.integrations.decisions_client import CandidateItem, EventIn, OutfitScoringRequest, WeatherIn, score_outfits
from app.models import WardrobeItem
from app.tools.context import OutfitOption, RunContext, ToolOutput

MAX_CANDIDATES = 18
TOP_K = 3
REPEAT_PENALTY = 0.07  # per item already chosen for an earlier event in this trip
REWEARABLE = ("outerwear", "shoes", "bags")
LABELS = {"vibe": "vibe", "dress_code": "dress code", "weather": "weather", "color": "color harmony", "freshness": "freshness"}


def _occasion_filter(items: list[WardrobeItem], event: dict[str, Any]) -> list[WardrobeItem]:
    text = f"{event.get('name', '')} {event.get('dress_code_hint', '')}".lower()
    if any(w in text for w in ("run", "athletic", "gym", "workout", "yoga")):
        sporty = [
            i for i in items
            if i.style == "sporty" or i.category == "activewear"
            or (i.category == "tops" and i.subcategory in ("t-shirt", "tank top"))
        ]
        return sporty or items
    pool = [i for i in items if i.style != "sporty" and i.category != "activewear"]
    if any(w in text for w in ("dressy", "formal", "upscale", "gala", "black tie", "business")):
        # Layers stay available regardless of formality: a casual jacket beats being cold.
        pool = [i for i in pool if i.formality != "casual" or i.category in ("accessories", "bags", "outerwear")]
    return pool or items


def _weather_for(ctx: RunContext, event: dict[str, Any], weather: Optional[dict[str, Any]]) -> WeatherIn:
    w = weather or {}
    day = ctx.weather_by_date.get(event.get("date") or "", {})
    temp = w.get("temp_f")
    if temp is None and day.get("high_f") is not None:
        temp = round((day["high_f"] + day["low_f"]) / 2) if day.get("low_f") is not None else day["high_f"]
    pct = day.get("precip_pct")
    precip = w.get("precipitation")
    if precip is None:
        precip = (pct or 0) >= 50
    return WeatherIn(temp_f=temp, precipitation=bool(precip), precip_pct=pct)


def _hint(scores: dict[str, float]) -> str:
    parts = sorted(((k, v) for k, v in scores.items() if k != "overall"), key=lambda kv: -kv[1])
    top = ", ".join(f"{LABELS[k]} {v:.2f}" for k, v in parts[:2])
    weakest = parts[-1]
    return f"Strongest on {top}; weakest on {LABELS[weakest[0]]} ({weakest[1]:.2f})."


def build_and_score_outfits(
    ctx: RunContext,
    event: dict[str, Any],
    vibe: str = "",
    weather: Optional[dict[str, Any]] = None,
) -> ToolOutput:
    event = {"name": str(event.get("name") or "Outfit"), "dress_code_hint": event.get("dress_code_hint"), "date": event.get("date")}
    with Session(engine) as session:
        closet = list(session.exec(select(WardrobeItem)))
    by_id = {i.id: i for i in closet}
    pool = _occasion_filter(closet, event)
    w = _weather_for(ctx, event, weather)

    data = [
        gen.ItemData(
            id=i.id, category=i.category, name=i.name, subcategory=i.subcategory, color=i.color, style=i.style,
            season=i.season, last_worn=i.last_worn, times_worn=i.number_of_times_worn, is_favorite=i.is_favorite,
        )
        for i in pool
    ]
    wctx = gen.WeatherContext(temp_f=w.temp_f, precipitation=w.precipitation)
    seed = int(hashlib.sha256(f"{event['name']}{event['date']}".encode()).hexdigest()[:8], 16)
    filtered = gen.filter_for_weather(data, wctx)
    candidates = gen.diversify(gen.generate_candidates(filtered, wctx, today=ctx.today, seed=seed), k=MAX_CANDIDATES)
    if not candidates:
        return ToolOutput(
            result={"event": event, "options": [], "error": "No valid outfit combinations in the closet for this event."},
            title=f"No outfits possible for {event['name']}",
            kind="error",
        )

    def cand_item(item_id: str) -> CandidateItem:
        i = by_id[item_id]
        return CandidateItem(
            name=i.name, category=i.category, color=i.color, style=i.style, formality=i.formality, season=i.season,
            material=i.material, waterproof=i.waterproof,
            days_since_worn=None if i.last_worn is None else (ctx.today - i.last_worn).days,
            times_worn=i.number_of_times_worn,
        )

    req = OutfitScoringRequest(
        vibe=vibe or ctx.message,
        event=EventIn(**event),
        weather=w,
        candidates=[[cand_item(it.id) for it in c.items] for c in candidates],
    )
    scored = score_outfits(req)
    ctx.note_source("decisions", scored.meta.source)
    # Rotate across the trip: down-rank items already picked for earlier events.
    # Jackets, shoes and bags are normally re-worn on a trip, so they don't count.
    def repeat_cost(idx: int) -> float:
        return REPEAT_PENALTY * sum(
            ctx.used_items.get(i, 0) for i in candidates[idx].item_ids if by_id[i].category not in REWEARABLE
        )

    ranked = sorted(scored.scores, key=lambda s: -(s.scores.overall - repeat_cost(s.index)))
    rotated = ranked[0].index != max(scored.scores, key=lambda s: s.scores.overall).index
    for item_id in candidates[ranked[0].index].item_ids:
        ctx.used_items[item_id] = ctx.used_items.get(item_id, 0) + 1

    ctx.event_counter += 1
    ekey = f"E{ctx.event_counter}"
    options = []
    refs = []
    for rank, s in enumerate(ranked[:TOP_K]):
        cand = candidates[s.index]
        ref = f"{ekey}-{'ABC'[rank]}"
        scores = s.scores.model_dump()
        opt = OutfitOption(
            ref=ref, event_name=event["name"], event_date=event["date"], item_ids=cand.item_ids,
            item_names=[by_id[i].name for i in cand.item_ids], scores=scores, hint=_hint(scores),
        )
        ctx.outfits[ref] = opt
        refs.append(ref)
        options.append({"outfit_ref": ref, "items": opt.item_names, "scores": scores, "why": opt.hint})
    ctx.options_by_event[f"{event['name']}|{event['date']}"] = refs

    winner = options[0]["scores"]
    return ToolOutput(
        result={
            "event": event,
            "weather_used": w.model_dump(),
            "candidates_scored": len(candidates),
            "ranking": "overall score, lightly penalising pieces already planned earlier this trip",
            "scored_by": f"Decisions API ({scored.meta.source})",
            "options": options,
        },
        title=f"Scored {len(candidates)} outfit{'s' if len(candidates) != 1 else ''} for {event['name']} (Decisions API)",
        detail=f"Winner {winner['overall']:.2f} overall · " + options[0]["why"]
        + (" · Rotated to avoid repeating pieces from earlier this trip" if rotated else "")
        + (f" · {scored.meta.note}" if scored.meta.note else ""),
        source=scored.meta.source,
        kind="decision",
        decision={"winner_scores": winner, "candidates_scored": len(candidates), "questions": scored.meta.questions},
    )
