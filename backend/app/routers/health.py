"""Preflight: one tiny real Claude call per integration so we know they're green before going on stage."""

import time
from typing import Any

from fastapi import APIRouter

from app.config import get_settings
from app.core.vision import vision_configured
from app.integrations import recorder
from app.integrations import decisions_client
from app.integrations.anthropic_client import get_client, key_configured, short_error

router = APIRouter(prefix="/api/health", tags=["health"])


def _check_decisions() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        answer = decisions_client._create({
            "model": get_settings().decisions_model,
            "input": "A navy wool coat with a hood.",
            "questions": [{"type": "predicate", "name": "is_outerwear", "instructions": "Is this item outerwear?"}],
        })
        ms = int((time.perf_counter() - start) * 1000)
        recorder.log_call("decisions", "preflight", source="live", request={"questions": 1}, response=answer, duration_ms=ms)
        return {"ok": True, "ms": ms, "answer": answer.get("answers")}
    except Exception as exc:
        return {"ok": False, "ms": int((time.perf_counter() - start) * 1000), "error": short_error(exc)}


def _check_agents() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        s = get_settings()
        r = get_client().messages.create(
            model=s.agents_model,
            max_tokens=1024,
            system="Reply with the single word OK.",
            messages=[{"role": "user", "content": "ping"}],
            output_config={"effort": "low"},
        )
        ms = int((time.perf_counter() - start) * 1000)
        text = "".join(b.text for b in r.content if b.type == "text").strip()
        ok = r.stop_reason == "end_turn"
        recorder.log_call("agents", "preflight", source="live", request={"input": "ping"},
                          response={"text": text, "stop_reason": r.stop_reason, "model": r.model}, duration_ms=ms)
        return {"ok": ok, "ms": ms, "reply": text, "stop_reason": r.stop_reason}
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
        msg = "ANTHROPIC_API_KEY is not set in backend/.env"
        return {**base, "key_configured": False, "decisions": {"ok": False, "error": msg}, "agents": {"ok": False, "error": msg}}
    return {**base, "key_configured": True, "decisions": _check_decisions(), "agents": _check_agents()}
