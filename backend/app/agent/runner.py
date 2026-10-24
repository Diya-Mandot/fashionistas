"""Runs one stylist request in a background thread and persists the trace as it grows,
so the UI can poll GET /api/stylist/runs/{id} and animate steps in."""

from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlmodel import Session

from app.agent.plan import fallback_submission
from app.config import get_settings
from app.db import engine
from app.integrations.agents_client import build_goal, run_agent
from app.models import AgentRunRecord
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


def start_run(message: str, home_city: Optional[str] = None) -> str:
    home = (home_city or get_settings().home_city).strip() or get_settings().home_city
    with Session(engine) as session:
        rec = AgentRunRecord(message=message, home_city=home)
        session.add(rec)
        session.commit()
        run_id = rec.id
    t = threading.Thread(target=_execute, args=(run_id, message, home), daemon=True)
    _threads[run_id] = t
    t.start()
    return run_id


def wait(run_id: str, timeout: float = 240) -> None:
    t = _threads.get(run_id)
    if t:
        t.join(timeout)


def _execute(run_id: str, message: str, home: str) -> None:
    p = _Persist(run_id)
    total = Timer()
    today = date.today()
    ctx = RunContext(run_id=run_id, message=message, today=today, home_city=home, emit=p.emit)
    p.emit(TraceStep(kind="input", title="Your request", detail=message, source="local"))
    agent_source = "mock"
    try:
        run = run_agent(
            build_goal(today, home),
            tool_specs(),
            {"message": message, "today": today, "home_city": home},
            execute=lambda name, args: dispatch(ctx, name, args),
            emit=p.emit,
        )
        agent_source = run.source
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
