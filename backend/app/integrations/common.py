"""Shared adapter contracts and local replay storage.

Only validated results are recorded. Request bodies, image bytes, and keys are
never written. Results can contain personal information; this file stays local.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import Settings

T = TypeVar("T")


class AdapterError(RuntimeError):
    """A safe, user-visible failure without provider request bodies or secrets."""


class AdapterResult(BaseModel, Generic[T]):
    data: T
    source: Literal["live", "replay", "mock"]
    recorded_at: str | None = None
    warnings: list[str] = []


def make_client(settings: Settings) -> AsyncOpenAI:
    if not settings.openai_api_key.strip():
        raise AdapterError("OPENAI_API_KEY is required for live mode.")
    # The SDK retries network errors, 408, 409, 429 and 5xx with Retry-After.
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.api_timeout_seconds,
        max_retries=settings.api_max_retries,
    )


def fingerprint(operation: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"version": 1, "operation": operation, "payload": payload},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class Recordings:
    def __init__(self, path: Path):
        self.path = path

    def read(self, key: str) -> tuple[dict, str]:
        if self.path.exists():
            # Keep the newest valid recording. Ignore incomplete final lines.
            match = None
            for line in self.path.read_text().splitlines():
                try:
                    entry = json.loads(line)
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("fingerprint") == key:
                        if isinstance(entry["data"], dict) and isinstance(entry["recorded_at"], str):
                            match = (entry["data"], entry["recorded_at"])
                except (ValueError, KeyError, TypeError):
                    continue
            if match is not None:
                return match
        raise AdapterError("No matching live recording exists. Run this request live first.")

    def write(self, key: str, data: BaseModel) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"fingerprint": key, "recorded_at": timestamp, "data": data.model_dump(mode="json")}
        encoded = (json.dumps(entry, allow_nan=False) + "\n").encode()
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "ab", closefd=False) as stream:
                stream.write(encoded)
        finally:
            os.close(fd)
        return timestamp


def complete_live(data: T, key: str, recordings: Recordings) -> AdapterResult[T]:
    try:
        timestamp = recordings.write(key, data)
    except OSError:
        return AdapterResult(data=data, source="live", warnings=["Live call succeeded; local recording failed."])
    return AdapterResult(data=data, source="live", recorded_at=timestamp)
