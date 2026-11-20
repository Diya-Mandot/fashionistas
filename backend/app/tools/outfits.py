"""build_and_score_outfits: the ported rules generator narrows the closet to ≤18
sensible combos, then Claude scores each one on five criteria.

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
from app.text_rules import is_athletic
from app.tools.context import OutfitOption, RunContext, ToolOutput

MAX_CANDIDATES = 18
TOP_K = 3
REPEAT_PENALTY = 0.07  # per item already chosen for an earlier event in this trip
REWEARABLE = ("outerwear", "shoes", "bags")
# In distinct mode these may repeat across options when nothing else is left; clothing never does.
SHAREABLE = ("shoes", "bags", "accessories")
LABELS = {"vibe": "vibe", "dress_code": "dress code", "weather": "weather", "color": "color harmony", "freshness": "freshness"}


def _occasion_filter(items: list[WardrobeItem], event: dict[str, Any]) -> list[WardrobeItem]:
    text = f"{event.get('name', '')} {event.get('dress_code_hint', '')}".lower()
    if is_athletic(text):
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


def pick_distinct(cands: list, ids_of, by_id: dict[str, WardrobeItem], limit: int) -> list:
    """Greedy, in the given (best-first) order: options that share no piece at all, then, if
    still short, options that share only shoes/bags/accessories. Never repeats clothing, so it
    may return fewer than `limit`."""
    chosen: list = []
    for strict in (True, False):
        for c in cands:
            if len(chosen) >= limit:
                return chosen
            if any(c is o for o in chosen):
                continue
            ids = set(ids_of(c))
            if all(
                not (shared := ids & set(ids_of(o)))
                or (not strict and all(by_id[i].category in SHAREABLE for i in shared))
                for o in chosen
            ):
                chosen.append(c)
    return chosen


def build_and_score_outfits(
    ctx: RunContext,
    event: dict[str, Any],
    vibe: str = "",
    weather: Optional[dict[str, Any]] = None,
    top_k: int = TOP_K,
    exclude: Optional[list[frozenset[str]]] = None,
    distinct: bool = False,
) -> ToolOutput:
    """`top_k`, `exclude` (item-id sets to skip, e.g. outfits already shown) and `distinct`
    (options never share clothing; may return fewer than top_k) are for server-side callers
    such as the daily outfit picker; the agent's tool schema omits them."""
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
    ranked_all = gen.generate_candidates(
        filtered, wctx, today=ctx.today, seed=seed, preferred_colors=ctx.preferred_colors,
    )
    if exclude:
        ranked_all = [c for c in ranked_all if c.key not in exclude]
    if distinct:
        # Lead the shortlist with the largest non-overlapping set the closet allows, so Claude
        # scores enough genuinely different looks; fill the rest with near-variants as usual.
        spread = pick_distinct(ranked_all, lambda c: c.item_ids, by_id, MAX_CANDIDATES)
        candidates = spread + gen.diversify([c for c in ranked_all if c not in spread], k=MAX_CANDIDATES - len(spread))
    elif wctx.wants_outerwear:
        # Cold or wet: make sure layered outfits are well represented in the shortlist.
        layered = [c for c in ranked_all if any(by_id[i].category == "outerwear" for i in c.item_ids)]
        bare = [c for c in ranked_all if c not in layered]
        half = MAX_CANDIDATES // 2
        candidates = gen.diversify(layered, k=half) + gen.diversify(bare, k=MAX_CANDIDATES - min(half, len(layered)))
    else:
        candidates = gen.diversify(ranked_all, k=MAX_CANDIDATES)
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

    palettes = [gen.assess_palette(c.items, ctx.preferred_colors) for c in candidates]
    ranked = sorted(
        scored.scores,
        key=lambda s: -(s.scores.overall - repeat_cost(s.index) + gen.PALETTE_BONUS * (palettes[s.index][1] or 0)),
    )
    rotated = ranked[0].index != max(scored.scores, key=lambda s: s.scores.overall).index
    for item_id in candidates[ranked[0].index].item_ids:
        ctx.used_items[item_id] = ctx.used_items.get(item_id, 0) + 1

    ctx.event_counter += 1
    ekey = f"E{ctx.event_counter}"
    options = []
    refs = []
    picks = pick_distinct(ranked, lambda s: candidates[s.index].item_ids, by_id, top_k) if distinct else ranked[:top_k]
    for rank, s in enumerate(picks):
        cand = candidates[s.index]
        ref = f"{ekey}-{chr(ord('A') + rank)}"
        scores = s.scores.model_dump()
        hint = _hint(scores)
        palette_matches, palette_score = palettes[s.index]
        if palette_score is not None:
            scores["palette"] = palette_score
        opt = OutfitOption(
            ref=ref, event_name=event["name"], event_date=event["date"], item_ids=cand.item_ids,
            item_names=[by_id[i].name for i in cand.item_ids], scores=scores, hint=hint,
            palette_matches=palette_matches,
        )
        ctx.outfits[ref] = opt
        refs.append(ref)
        options.append({"outfit_ref": ref, "items": opt.item_names, "scores": scores, "why": opt.hint,
                        "palette_matches": opt.palette_matches})
    ctx.options_by_event[f"{event['name']}|{event['date']}"] = refs

    winner = options[0]["scores"]
    palette_score = winner.get("palette")
    palette_bonus = gen.PALETTE_BONUS * (palette_score or 0)
    return ToolOutput(
        result={
            "event": event,
            "weather_used": w.model_dump(),
            "candidates_scored": len(candidates),
            "ranking": "Overall score with adjustments for repeats and preferred colors worn near the face",
            "palette_weight": gen.PALETTE_BONUS if ctx.preferred_colors else 0,
            "winner_palette_bonus": round(palette_bonus, 3),
            "scored_by": f"Claude ({scored.meta.source})",
            "options": options,
        },
        title=f"Scored {len(candidates)} outfit{'s' if len(candidates) != 1 else ''} for {event['name']} (Claude)",
        detail=f"Winner {winner['overall']:.2f} overall · " + options[0]["why"]
        + (f" · Personal colors {palette_score:.2f} (+{palette_bonus:.2f} to ranking)" if palette_score is not None else "")
        + (" · Ranking adjusted for repeats or color preferences" if rotated else "")
        + (f" · {scored.meta.note}" if scored.meta.note else ""),
        source=scored.meta.source,
        kind="decision",
        decision={"winner_scores": winner, "candidates_scored": len(candidates), "questions": scored.meta.questions},
    )
