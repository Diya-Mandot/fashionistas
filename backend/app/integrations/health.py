"""Preflight: one tiny real call to each API, never falling back.

The agents check also round-trips a function tool, so a green result proves
the whole tool loop works with environment type `none`.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from app.config import get_settings
from app.integrations import recorder
from app.integrations.agents_client import AGENTS_TIMEOUT_S
from app.integrations.openai_client import get_client, key_configured, short_error

PING_TOKEN = "eco-pong-7"


def _timed(api: str, request: dict[str, Any], call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        detail, ok, error = call(), True, None
    except Exception as exc:
        detail, ok, error = {}, False, short_error(exc)
    ms = int((time.perf_counter() - start) * 1000)
    recorder.log_call(api, "health", source="live", request=request, response=detail or None, error=error, duration_ms=ms)
    return {"ok": ok, "ms": ms, **({"error": error} if error else detail)}


def check_decisions() -> dict[str, Any]:
    settings = get_settings()
    request = {
        "model": settings.decisions_model,
        "input": "A yellow PVC raincoat with a hood.",
        "questions": [{"type": "predicate", "name": "waterproof", "instructions": "This item is waterproof."}],
    }

    def call() -> dict[str, Any]:
        response = get_client().decisions.create(**request).model_dump(mode="json")
        return {"model": response["model"], "answer": response["answers"][0]}

    return {"api": "decisions", "mode": settings.decisions_mode, **_timed("decisions", request, call)}


def check_agents() -> dict[str, Any]:
    settings = get_settings()
    request = {
        "model": settings.agents_model,
        "instructions": "Call the `ping` tool exactly once, then reply with only the token it returned.",
        "input": "Run the preflight check.",
    }

    def call() -> dict[str, Any]:
        calls: list[dict[str, Any]] = []

        def ping(args: dict[str, Any]) -> dict[str, Any]:
            calls.append(args)
            return {"token": PING_TOKEN}

        with get_client().beta.agents.sessions.create(
            agent={
                "model": request["model"],
                "instructions": request["instructions"],
                "tools": [{
                    "type": "function",
                    "name": "ping",
                    "description": "Returns a token proving the tool loop works.",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                }],
            },
            environment={"type": "none"},
            input=request["input"],
            stream=True,
            tool_handlers={"ping": ping},
            timeout=AGENTS_TIMEOUT_S,
        ).with_result_collection() as stream:
            result = stream.get_final_result()
        text = result.output_text.strip()
        if not calls:
            raise RuntimeError(f"agent never called the ping tool (replied {text[:80]!r})")
        if PING_TOKEN not in text:
            raise RuntimeError(f"agent called ping but replied {text[:80]!r}")
        return {"model": request["model"], "session_id": result.session_id, "tool_calls": len(calls), "reply": text}

    return {"api": "agents", "mode": settings.agents_mode, **_timed("agents", request, call)}


def check_all() -> dict[str, Any]:
    if not key_configured():
        return {"key_present": False, "ok": False, "checks": []}
    checks = [check_decisions(), check_agents()]
    return {"key_present": True, "ok": all(c["ok"] for c in checks), "checks": checks}
