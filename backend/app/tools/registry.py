"""Tool registry: each tool is a plain Python function + a JSON schema.

The schemas are what the Agents API sees; dispatch() runs a call, times it and
records a trace step. The agent decides the order; nothing here sequences tools.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from app.agent.plan import SUBMIT_PLAN_SCHEMA, assemble_plan
from app.tools.calendar_tool import read_calendar
from app.tools.closet_tool import query_closet
from app.tools.context import RunContext, ToolOutput
from app.tools.gaps import find_closet_gaps
from app.tools.outfits import build_and_score_outfits
from app.tools.secondhand import suggest_secondhand_item
from app.tools.weather import get_weather_forecast
from app.trace import Timer, TraceStep, truncate

DATE = {"type": "string", "description": "YYYY-MM-DD"}


def submit_plan(ctx: RunContext, **submission: Any) -> ToolOutput:
    plan, warnings = assemble_plan(ctx, submission)
    ctx.plan = plan.model_dump()
    n_events = sum(len(d.events) for d in plan.days)
    missing = [e.name for d in plan.days for e in d.events if e.outfit is None]
    result: dict[str, Any] = {"accepted": True, "days": len(plan.days), "events": n_events, "gaps": len(plan.gaps)}
    if warnings:
        result["warnings"] = warnings
    if missing:
        result["events_without_outfit"] = missing
    detail = "; ".join(warnings) if warnings else "All outfit refs and item IDs verified against the closet"
    return ToolOutput(
        result=result,
        title=f"Validated plan: {len(plan.days)} days, {n_events} events, {len(plan.gaps)} gap{'s' if len(plan.gaps) != 1 else ''}",
        detail=detail,
        kind="validation",
    )


TOOLS: dict[str, tuple[Callable[..., ToolOutput], str, dict[str, Any]]] = {
    "get_weather_forecast": (
        get_weather_forecast,
        "Daily forecast (°F high/low, precipitation chance) for a city and date range. Real data.",
        {
            "type": "object",
            "properties": {"city": {"type": "string"}, "start_date": DATE, "end_date": DATE},
            "required": ["city", "start_date", "end_date"],
        },
    ),
    "read_calendar": (
        read_calendar,
        "The user's calendar events (name, date, time, location, dress code hint) in a date range.",
        {"type": "object", "properties": {"start_date": DATE, "end_date": DATE}, "required": ["start_date", "end_date"]},
    ),
    "query_closet": (
        query_closet,
        "List items in the user's closet with attributes and wear history. Filters are optional.",
        {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": ["tops", "bottoms", "dresses", "outerwear", "shoes", "accessories", "bags", "activewear"]},
                        "formality": {"type": "string", "enum": ["casual", "smart casual", "business", "formal"]},
                        "season": {"type": "string"},
                        "color": {"type": "string"},
                        "waterproof": {"type": "boolean"},
                    },
                }
            },
        },
    ),
    "build_and_score_outfits": (
        build_and_score_outfits,
        "For one event: build candidate outfits from the closet and have the Decisions API score them on vibe, "
        "dress code, weather, color harmony and freshness. Returns the top options as outfit_refs.",
        {
            "type": "object",
            "properties": {
                "event": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "dress_code_hint": {"type": "string"}, "date": DATE},
                    "required": ["name", "date"],
                },
                "weather": {
                    "type": "object",
                    "properties": {"temp_f": {"type": "number"}, "precipitation": {"type": "boolean"}},
                },
                "vibe": {"type": "string", "description": "The look the user asked for, in their words"},
            },
            "required": ["event", "vibe"],
        },
    ),
    "find_closet_gaps": (
        find_closet_gaps,
        "Detect needs the closet can't meet for these events and forecast (e.g. rain and no waterproof layer). "
        "Severity is rated by the Decisions API.",
        {
            "type": "object",
            "properties": {
                "events": {"type": "array", "items": {"type": "object"}},
                "weather_days": {"type": "array", "items": {"type": "object"}},
            },
        },
    ),
    "suggest_secondhand_item": (
        suggest_secondhand_item,
        "Suggest a secondhand item to fill a closet gap. Returns a suggestion_ref and marketplace search links.",
        {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "e.g. 'black trench coat'"},
                "why": {"type": "string"},
                "size": {"type": "string"},
            },
            "required": ["description"],
        },
    ),
    "submit_plan": (
        submit_plan,
        "Submit the final day-by-day plan. Reference outfits ONLY by outfit_ref and suggestions by suggestion_ref. "
        "The server validates every ref and returns warnings you should fix.",
        SUBMIT_PLAN_SCHEMA,
    ),
}


def tool_specs() -> list[dict[str, Any]]:
    return [{"type": "function", "name": n, "description": d, "parameters": p} for n, (_f, d, p) in TOOLS.items()]


def dispatch(ctx: RunContext, name: str, args: Any) -> tuple[dict[str, Any], bool]:
    """Run one tool call, emitting a running step then the finished step. Returns (result, ok)."""
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except json.JSONDecodeError:
            args = {}
    args = args if isinstance(args, dict) else {}
    step = TraceStep(kind="tool_call", tool=name, title=f"Calling {name}…", args=truncate(args), status="running")
    ctx.emit(step)
    timer = Timer()
    entry = TOOLS.get(name)
    if entry is None:
        out = ToolOutput(result={"error": f"Unknown tool {name}"}, title=f"Unknown tool {name}", kind="error")
        ok = False
    else:
        try:
            out = entry[0](ctx, **args)
            ok = out.kind != "error"
        except TypeError as exc:
            out = ToolOutput(result={"error": f"Bad arguments: {exc}"}, title=f"{name}: bad arguments", kind="error")
            ok = False
        except Exception as exc:  # never let a tool crash the run
            out = ToolOutput(result={"error": f"{type(exc).__name__}: {exc}"}, title=f"{name} failed", kind="error")
            ok = False
    step = step.model_copy(
        update={
            "kind": out.kind,
            "title": out.title,
            "detail": out.detail,
            "result": truncate(out.result),
            "source": out.source,
            "duration_ms": timer.ms,
            "status": "error" if not ok else "done",
            "decision": out.decision,
        }
    )
    ctx.emit(step)
    return out.result, ok
