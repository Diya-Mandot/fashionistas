"""API call log + record/replay store.

Every live call is appended to logs/api_calls.jsonl. Successful live responses are
also saved under recordings/<api>/<fingerprint>.json so the exact same request can
be replayed honestly (labelled "replayed") if the network or API fails mid-demo.
Keys are never part of the payloads we log.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from app.config import BACKEND_DIR

Source = Literal["live", "replay", "mock", "rule", "local"]

LOG_PATH = BACKEND_DIR / "logs" / "api_calls.jsonl"
RECORDINGS_DIR = BACKEND_DIR / "recordings"
_lock = threading.Lock()
_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{20,})")


def _redact(obj: Any) -> Any:
    if isinstance(obj, str):
        if obj.startswith("data:image/"):
            return obj[:48] + f"…[{len(obj)} chars]"
        return _SECRET_RE.sub("[REDACTED]", obj)
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if "key" in k.lower() and isinstance(v, str) else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def fingerprint(api: str, payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(f"{api}:{canonical}".encode()).hexdigest()[:24]


def log_call(
    api: str,
    operation: str,
    *,
    source: Source,
    request: Any = None,
    response: Any = None,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "api": api,
        "operation": operation,
        "source": source,
        "duration_ms": duration_ms,
        "error": error,
        "request": _redact(request),
        "response": _redact(response),
    }
    with _lock, LOG_PATH.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def save_recording(api: str, fp: str, request: Any, response: Any) -> None:
    folder = RECORDINGS_DIR / api
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "request": _redact(request),
        "response": response,
    }
    (folder / f"{fp}.json").write_text(json.dumps(data, default=str, indent=1))


def load_recording(api: str, fp: str) -> Optional[dict[str, Any]]:
    path = RECORDINGS_DIR / api / f"{fp}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def recording_count(api: str) -> int:
    folder = RECORDINGS_DIR / api
    return len(list(folder.glob("*.json"))) if folder.exists() else 0


def recorded_at_label(recording: dict[str, Any]) -> str:
    try:
        ts = datetime.fromisoformat(recording["recorded_at"]).astimezone()
        return ts.strftime("%b %d, %H:%M")
    except (KeyError, ValueError):
        return "an earlier live run"
