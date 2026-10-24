"""Plan models and server-side assembly/validation of the agent's submission.

The agent submits outfit refs ("E1-A"); we map them to real item IDs, attach
scores, weather and secondhand suggestions, and drop anything unknown
(noting it in the trace). Model output is never trusted blindly.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import engine
from app.models import WardrobeItem
from app.tools.context import RunContext
from app.tools.secondhand import links_for


class Scores(BaseModel):
    overall: float
    vibe: float
    dress_code: float
    weather: float
    color: float
    freshness: float


class OutfitPick(BaseModel):
    item_ids: list[str]
    scores: Scores
    rationale: str
    ref: Optional[str] = None


class PlanEvent(BaseModel):
    name: str
    time: Optional[str] = None
    dress_code: Optional[str] = None
    outfit: Optional[OutfitPick] = None
    alternates: list[OutfitPick] = Field(default_factory=list)


class DayWeather(BaseModel):
    high_f: Optional[float] = None
    low_f: Optional[float] = None
    precip_pct: Optional[float] = None
    summary: Optional[str] = None


class PlanDay(BaseModel):
    date: str
    weather: Optional[DayWeather] = None
    events: list[PlanEvent]


class SecondhandSuggestion(BaseModel):
    description: str
    why: str
    links: list[dict[str, str]]


class Gap(BaseModel):
    need: str
    severity: str
    reason: str
    suggestion: Optional[SecondhandSuggestion] = None


class Trip(BaseModel):
    city: str
    start: str
    end: str
    summary: str


class PackingEntry(BaseModel):
    item_id: str
    used_on: list[str]


class Plan(BaseModel):
    trip: Trip
    days: list[PlanDay]
    packing_list: list[PackingEntry]
    gaps: list[Gap]
    notes: list[str] = Field(default_factory=list)


# JSON schema for the submit_plan tool (what the agent fills in).
SUBMIT_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "trip": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "start": {"type": "string", "description": "YYYY-MM-DD"},
                "end": {"type": "string", "description": "YYYY-MM-DD"},
                "summary": {"type": "string", "description": "A short title, at most 8 words, e.g. '3 days, cool and drizzly'. No full sentences."},
            },
            "required": ["city", "start", "end", "summary"],
        },
        "days": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "time": {"type": "string"},
                                "dress_code": {"type": "string"},
                                "outfit_ref": {"type": "string", "description": "An outfit_ref returned by build_and_score_outfits, e.g. 'E2-A'"},
                                "alternate_refs": {"type": "array", "items": {"type": "string"}},
                                "rationale": {"type": "string", "description": "One sentence on why this outfit wins for the vibe, event and weather"},
                            },
                            "required": ["name", "outfit_ref", "rationale"],
                        },
                    },
                },
                "required": ["date", "events"],
            },
        },
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "need": {"type": "string"},
                    "severity": {"type": "string", "enum": ["must-have", "nice-to-have", "optional"]},
                    "reason": {"type": "string"},
                    "suggestion_ref": {"type": "string", "description": "A suggestion_ref from suggest_secondhand_item, e.g. 'S1'"},
                },
                "required": ["need", "severity", "reason"],
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["trip", "days", "gaps"],
}


def _short_event(name: str) -> str:
    n = name.lower()
    for key, label in (("dinner", "dinner"), ("brunch", "brunch"), ("run", "run"), ("show", "show"), ("conference", "conference"), ("gallery", "gallery")):
        if key in n:
            return label
    return name.split(" ")[0].lower()


def assemble_plan(ctx: RunContext, submission: dict[str, Any]) -> tuple[Plan, list[str]]:
    """Map refs to real items and build the validated Plan. Returns (plan, warnings)."""
    warnings: list[str] = []
    with Session(engine) as session:
        closet_ids = set(session.exec(select(WardrobeItem.id)))

    def pick(ref: Optional[str], rationale: Optional[str] = None) -> Optional[OutfitPick]:
        if not ref:
            return None
        opt = ctx.outfits.get(ref.strip())
        if not opt:
            warnings.append(f"Dropped unknown outfit ref {ref!r} (not returned by build_and_score_outfits)")
            return None
        ids = [i for i in opt.item_ids if i in closet_ids]
        if len(ids) != len(opt.item_ids):
            warnings.append(f"Dropped {len(opt.item_ids) - len(ids)} item(s) from {ref} that are no longer in the closet")
        return OutfitPick(item_ids=ids, scores=Scores(**opt.scores), rationale=(rationale or opt.hint).strip(), ref=opt.ref)

    trip_in = submission.get("trip") or {}
    days: list[PlanDay] = []
    used: dict[str, list[str]] = {}
    for d in submission.get("days") or []:
        day_date = str(d.get("date", ""))
        events: list[PlanEvent] = []
        for e in d.get("events") or []:
            # Defensive: an agent might put raw item IDs here; keep only real ones.
            for raw_id in e.get("item_ids") or []:
                if raw_id not in closet_ids:
                    warnings.append(f"Dropped unknown item id {raw_id!r}")
            outfit = pick(e.get("outfit_ref"), e.get("rationale"))
            alt_refs = e.get("alternate_refs") or []
            if not alt_refs and outfit and outfit.ref:
                prefix = outfit.ref.split("-")[0]
                alt_refs = [r for r in ctx.outfits if r.startswith(prefix + "-") and r != outfit.ref]
            alternates = [a for a in (pick(r) for r in alt_refs) if a]
            events.append(PlanEvent(name=str(e.get("name", "Event")), time=e.get("time"), dress_code=e.get("dress_code"), outfit=outfit, alternates=alternates))
            if outfit:
                try:
                    label = f"{date.fromisoformat(day_date).strftime('%a')} {_short_event(str(e.get('name', '')))}"
                except ValueError:
                    label = _short_event(str(e.get("name", "")))
                for iid in outfit.item_ids:
                    used.setdefault(iid, [])
                    if label not in used[iid]:
                        used[iid].append(label)
        w = ctx.weather_by_date.get(day_date)
        days.append(PlanDay(date=day_date, weather=DayWeather(**{k: w.get(k) for k in ("high_f", "low_f", "precip_pct", "summary")}) if w else None, events=events))

    gaps: list[Gap] = []
    for g in submission.get("gaps") or []:
        sug = None
        ref = g.get("suggestion_ref")
        if ref and ref in ctx.suggestions:
            s = ctx.suggestions[ref]
            sug = SecondhandSuggestion(description=s["description"], why=s["why"], links=s["links"])
        elif ref:
            warnings.append(f"Dropped unknown suggestion ref {ref!r}")
        if sug is None:
            need = str(g.get("need", ""))
            match = next((s for s in ctx.suggestions.values() if any(w in s["description"].lower() for w in need.lower().split() if len(w) > 3)), None)
            if match:
                sug = SecondhandSuggestion(description=match["description"], why=match["why"], links=match["links"])
            elif g.get("severity") == "must-have":
                sug = SecondhandSuggestion(description=need, why=str(g.get("reason", "")), links=links_for(f"secondhand {need}"))
        gaps.append(Gap(need=str(g.get("need", "")), severity=str(g.get("severity", "nice-to-have")), reason=str(g.get("reason", "")), suggestion=sug))

    order = {iid: n for n, iid in enumerate(used)}
    packing = [PackingEntry(item_id=i, used_on=labels) for i, labels in sorted(used.items(), key=lambda kv: (-len(kv[1]), order[kv[0]]))]
    dates = [d.date for d in days if d.date]
    plan = Plan(
        trip=Trip(
            city=str(trip_in.get("city") or ctx.city or ctx.home_city),
            start=str(trip_in.get("start") or (min(dates) if dates else ctx.today.isoformat())),
            end=str(trip_in.get("end") or (max(dates) if dates else ctx.today.isoformat())),
            summary=str(trip_in.get("summary") or f"{len(days)} day plan"),
        ),
        days=days,
        packing_list=packing,
        gaps=gaps,
        notes=[str(n) for n in submission.get("notes") or []],
    )
    return plan, warnings


def fallback_submission(ctx: RunContext) -> dict[str, Any]:
    """Build a submission from what the tools produced if the agent never submitted one."""
    by_date: dict[str, list[dict[str, Any]]] = {}
    for key, refs in ctx.options_by_event.items():
        name, d = key.split("|", 1)
        ev = next((e for e in ctx.events_seen if e["name"] == name), {})
        by_date.setdefault(d if d != "None" else ctx.today.isoformat(), []).append(
            {"name": name, "time": ev.get("start_time"), "dress_code": ev.get("dress_code_hint"), "outfit_ref": refs[0], "alternate_refs": refs[1:]}
        )
    gaps = [
        {"need": g["need"], "severity": g["severity"], "reason": g["reason"]}
        for g in ctx.gaps
    ]
    return {"trip": {}, "days": [{"date": d, "events": evs} for d, evs in sorted(by_date.items())], "gaps": gaps}
