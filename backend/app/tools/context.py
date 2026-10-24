"""Per-run state shared by the agent's tools.

Outfits and secondhand suggestions are registered under short refs ("E1-A",
"S1"). The agent only ever references those refs; item IDs are mapped back
server-side, so the model can't invent closet IDs (capstone outfit_curator pattern).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional

from app.trace import TraceStep


@dataclass
class OutfitOption:
    ref: str
    event_name: str
    event_date: Optional[str]
    item_ids: list[str]
    item_names: list[str]
    scores: dict[str, float]
    hint: str


@dataclass
class RunContext:
    run_id: str
    message: str
    today: date
    home_city: str
    emit: Callable[[TraceStep], None]
    home_coords: Optional[tuple[float, float]] = None
    city: Optional[str] = None
    weather_by_date: dict[str, dict[str, Any]] = field(default_factory=dict)
    events_seen: list[dict[str, Any]] = field(default_factory=list)
    outfits: dict[str, OutfitOption] = field(default_factory=dict)
    options_by_event: dict[str, list[str]] = field(default_factory=dict)
    suggestions: dict[str, dict[str, Any]] = field(default_factory=dict)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    plan: Optional[dict[str, Any]] = None
    sources: dict[str, set[str]] = field(default_factory=dict)
    event_counter: int = 0
    used_items: dict[str, int] = field(default_factory=dict)

    def note_source(self, api: str, source: str) -> None:
        self.sources.setdefault(api, set()).add(source)


@dataclass
class ToolOutput:
    result: dict[str, Any]
    title: str
    detail: Optional[str] = None
    source: str = "local"
    kind: str = "tool_call"
    decision: Optional[dict[str, Any]] = None
