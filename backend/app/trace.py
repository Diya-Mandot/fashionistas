"""Trace steps shown in the UI's Agent Trace panel (and the Scan trace)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

StepKind = Literal["input", "thinking", "tool_call", "decision", "message", "validation", "fallback", "error", "final"]


class TraceStep(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    kind: StepKind
    tool: Optional[str] = None
    title: str
    detail: Optional[str] = None
    args: Any = None
    result: Any = None
    source: Optional[str] = None
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: Optional[int] = None
    status: Literal["running", "done", "error"] = "done"
    decision: Optional[dict[str, Any]] = None


class Timer:
    def __init__(self) -> None:
        self.start = time.perf_counter()

    @property
    def ms(self) -> int:
        return int((time.perf_counter() - self.start) * 1000)


def truncate(obj: Any, max_list: int = 30, max_str: int = 2000) -> Any:
    """Keep trace payloads readable: cap long lists/strings."""
    if isinstance(obj, str):
        return obj if len(obj) <= max_str else obj[:max_str] + f"… [{len(obj) - max_str} more chars]"
    if isinstance(obj, list):
        out = [truncate(v, max_list, max_str) for v in obj[:max_list]]
        if len(obj) > max_list:
            out.append(f"… {len(obj) - max_list} more")
        return out
    if isinstance(obj, dict):
        return {k: truncate(v, max_list, max_str) for k, v in obj.items()}
    return obj
