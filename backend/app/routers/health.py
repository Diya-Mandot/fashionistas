"""Preflight: one tiny real call to each API so we know they're green before going on stage."""

import time
from typing import Any

from fastapi import APIRouter

from app.config import get_settings
from app.core.vision import vision_configured
from app.integrations import recorder
from app.integrations.openai_client import get_client, key_configured, short_error

router = APIRouter(prefix="/api/health", tags=["health"])


def _check_decisions() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        d = get_client().decisions.create(
            model=get_settings().decisions_model,
            input="A navy wool coat with a hood.",
            questions=[{"type": "predicate", "name": "is_outerwear", "instructions": "Is this item outerwear?"}],
        )
        ms = int((time.perf_counter() - start) * 1000)
        answer = d.model_dump(mode="json")
        recorder.log_call("decisions", "preflight", source="live", request={"questions": 1}, response=answer, duration_ms=ms)
        return {"ok": True, "ms": ms, "answer": answer.get("answers")}
    except Exception as exc:
        return {"ok": False, "ms": int((time.perf_counter() - start) * 1000), "error": short_error(exc)}


def _check_agents() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        client = get_client()
        stream = client.beta.agents.sessions.create(
            agent={"model": get_settings().agents_model, "instructions": "Reply with the single word OK.", "reasoning": {"effort": "low"}},
            environment={"type": "none"},
            input="ping",
            stream=True,
        )
        text, types = None, []
        with stream:
            for ev in stream:
                d = ev.to_dict() if hasattr(ev, "to_dict") else dict(ev)
                types.append(d.get("type"))
                if d.get("type") == "agent.session.turn.output_text.done":
                    text = d.get("text")
                if d.get("type") in ("agent.session.turn.completed", "agent.session.turn.failed", "agent.session.failed", "error"):
                    break
                if time.perf_counter() - start > 60:
                    break
        ms = int((time.perf_counter() - start) * 1000)
        ok = "agent.session.turn.completed" in types
        recorder.log_call("agents", "preflight", source="live", request={"input": "ping"}, response={"text": text, "event_types": types[-30:]}, duration_ms=ms)
        return {"ok": ok, "ms": ms, "reply": text, "events": types[-8:]}
    except Exception as exc:
        return {"ok": False, "ms": int((time.perf_counter() - start) * 1000), "error": short_error(exc)}


@router.get("/apis")
def preflight() -> dict[str, Any]:
    s = get_settings()
    base = {
        "modes": {"agents": s.agents_mode, "decisions": s.decisions_mode},
        "recordings": {"agents": recorder.recording_count("agents"), "decisions": recorder.recording_count("decisions")},
        "vision_configured": vision_configured(),
    }
    if not key_configured():
        msg = "OPENAI_API_KEY is not set in backend/.env"
        return {**base, "key_configured": False, "decisions": {"ok": False, "error": msg}, "agents": {"ok": False, "error": msg}}
    return {**base, "key_configured": True, "decisions": _check_decisions(), "agents": _check_agents()}
