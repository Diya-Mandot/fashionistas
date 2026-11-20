"""Runs one stylist request in a background thread and persists the trace as it grows,
so the UI can poll GET /api/stylist/runs/{id} and animate steps in."""

from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from typing import Any, Optional

import anthropic
from sqlmodel import Session, select

from app.agent.plan import fallback_submission
from app.config import get_settings
from app.core.outfit_generator import normalize_color
from app.core.vision import ValidatedImage
from app.db import engine
from app.integrations.agents_client import build_goal, run_agent
from app.integrations.anthropic_client import ApiNotConfigured
from app.integrations.palette_client import analyze_palette, load_palette_evidence
from app.models import AgentRunRecord, WardrobeItem
from app.services.location import reverse_geocode
from app.tools.context import RunContext
from app.tools.registry import dispatch, submit_plan, tool_specs
from app.trace import Timer, TraceStep

_threads: dict[str, threading.Thread] = {}


class _Persist:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.steps: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def emit(self, step: TraceStep) -> None:
        data = step.model_dump()
        with self.lock:
            for n, s in enumerate(self.steps):
                if s["id"] == data["id"]:
                    self.steps[n] = data
                    break
            else:
                self.steps.append(data)
            self._save(trace=list(self.steps))

    def _save(self, **fields: Any) -> None:
        with Session(engine) as session:
            rec = session.get(AgentRunRecord, self.run_id)
            if rec is None:
                return
            for k, v in fields.items():
                setattr(rec, k, v)
            session.add(rec)
            session.commit()


def start_run(
    message: str, home_city: Optional[str] = None, location: Optional[dict[str, Any]] = None,
    preferred_colors: tuple[str, ...] = (),
    portrait: Optional[ValidatedImage] = None,
) -> str:
    home = (home_city or "").strip()
    coords = None
    if location:
        coords = (location["lat"], location["lon"])
        if not home:
            home = (location.get("city") or "").strip()
            if not home:
                place = reverse_geocode(*coords)
                home = place["city"] if place else ""
    home = home or get_settings().home_city
    with Session(engine) as session:
        rec = AgentRunRecord(message=message, home_city=home)
        session.add(rec)
        session.commit()
        run_id = rec.id
    colors = frozenset(filter(None, map(normalize_color, preferred_colors)))
    t = threading.Thread(target=_execute, args=(run_id, message, home, coords, colors, portrait), daemon=True)
    _threads[run_id] = t
    t.start()
    return run_id


def wait(run_id: str, timeout: float = 240) -> None:
    t = _threads.get(run_id)
    if t:
        t.join(timeout)


def _prepare_palette(ctx: RunContext, portrait: Optional[ValidatedImage]) -> None:
    manual = sorted(ctx.preferred_colors)
    if portrait is None:
        if manual:
            ctx.emit(TraceStep(
                kind="tool_call", tool="personal_palette", title="Used your preferred colors",
                detail=", ".join(manual), source="local", result={"colors_used_for_ranking": manual},
            ))
        return

    with Session(engine) as session:
        colors = session.exec(
            select(WardrobeItem.color)
            .where(WardrobeItem.category.in_(("tops", "dresses", "outerwear", "activewear")))
            .distinct().order_by(WardrobeItem.color).limit(60)
        )
        closet_colors = [color[:40] for color in colors if color and color.strip()]
    timer = Timer()
    evidence, evidence_source = load_palette_evidence()
    step = TraceStep(
        kind="tool_call", tool="personal_palette", title="Checking clothing colors from your photo",
        args={"profile_photo": True, "preferred_colors": manual, "closet_color_count": len(closet_colors),
              "research_source": evidence_source, "research_version": evidence.version,
              "research": evidence.model_dump(mode="json", exclude_none=True)["sources"]}, status="running",
    )
    ctx.emit(step)
    try:
        advice = analyze_palette(portrait, ctx.preferred_colors, closet_colors, evidence)
    except ApiNotConfigured:
        detail = "Live Claude scoring and an API key are required for photo suggestions."
    except (anthropic.APIError, ValueError, OSError):
        detail = "Claude could not return a photo palette for this run."
    else:
        suggested = frozenset(filter(None, map(normalize_color, advice.colors)))
        applied = suggested if advice.confidence == "moderate" else frozenset()
        assessment = f"{advice.confidence.capitalize()} confidence. {advice.summary}"
        provenance = {
            "llamapress": "LlamaPress research",
            "bundled": "Bundled research",
            "bundled_fallback": "Bundled research. LlamaPress was unavailable or returned invalid data.",
        }[evidence_source]
        detail = f"{provenance} · {assessment}"
        if applied:
            detail = f"{', '.join(sorted(applied))} · {detail}"
        ctx.preferred_colors |= applied
        ctx.note_source("palette", "live")
        ctx.emit(step.model_copy(update={
            "kind": "decision",
            "title": "Suggested colors from your photo" if applied else "Photo did not give a reliable palette",
            "detail": detail,
            "result": {"confidence": advice.confidence, "summary": advice.summary,
                       "photo_suggestions": sorted(applied), "colors_used_for_ranking": sorted(ctx.preferred_colors)},
            "source": "live", "status": "done", "duration_ms": timer.ms,
        }))
        return

    ctx.emit(step.model_copy(update={
        "kind": "fallback", "title": "Photo colors unavailable", "detail": detail,
        "result": {"colors_used_for_ranking": manual}, "source": "local", "status": "done",
        "duration_ms": timer.ms,
    }))


def _execute(
    run_id: str, message: str, home: str, coords: Optional[tuple[float, float]] = None,
    preferred_colors: frozenset[str] = frozenset(),
    portrait: Optional[ValidatedImage] = None,
) -> None:
    p = _Persist(run_id)
    total = Timer()
    today = date.today()
    ctx = RunContext(
        run_id=run_id, message=message, today=today, home_city=home, emit=p.emit, home_coords=coords,
        preferred_colors=preferred_colors,
    )
    p.emit(TraceStep(kind="input", title="Your request", detail=message, source="local",
                     args={"message": message, "home_city": home, "device_location": bool(coords)}))
    agent_source = "mock"
    try:
        _prepare_palette(ctx, portrait)
        run = run_agent(
            build_goal(today, home, located=bool(coords)),
            tool_specs(),
            {"message": message, "today": today, "home_city": home},
            execute=lambda name, args: dispatch(ctx, name, args),
            emit=p.emit,
        )
        agent_source = run.source
        if ctx.plan is None and not ctx.options_by_event:
            # Nothing to plan yet (e.g. "hi"): surface the agent's question instead of an empty plan.
            p.emit(TraceStep(kind="final", title="The stylist needs a bit more detail",
                             detail=run.final_text or "Tell me where you're going and the vibe you want.",
                             duration_ms=total.ms, source=run.source))
            p._save(status="needs_input", plan=None, sources={"agent": agent_source},
                    finished_at=datetime.now(timezone.utc))
            return
        if ctx.plan is None:
            p.emit(TraceStep(kind="fallback", title="Agent didn't submit a plan; assembling one from its scored outfits", source="local"))
            out = submit_plan(ctx, **fallback_submission(ctx))
            p.emit(TraceStep(kind=out.kind, tool="submit_plan", title=out.title, detail=out.detail, result=out.result, source="local"))
        status, error = "completed", None
    except Exception as exc:  # last line of defence: never leave a run hanging
        status, error = ("completed" if ctx.plan else "failed"), f"{type(exc).__name__}: {exc}"
        p.emit(TraceStep(kind="error", title="Something went wrong", detail=error, status="error", source="local"))

    sources = {"agent": agent_source, **{k: sorted(v) for k, v in ctx.sources.items()}}
    p.emit(TraceStep(kind="final", title="Plan ready" if ctx.plan else "No plan produced", detail=f"Total {total.ms / 1000:.1f}s", duration_ms=total.ms, source="local"))
    p._save(status=status, plan=ctx.plan, sources=sources, error=error, finished_at=datetime.now(timezone.utc))
