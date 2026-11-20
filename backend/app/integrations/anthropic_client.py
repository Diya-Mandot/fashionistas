"""Shared Anthropic (Claude) client for the agent loop and the scoring/classification calls."""

from functools import lru_cache
from typing import Any, Optional

import anthropic

from app.config import get_settings

# Server-side refusal fallback: if the requested model declines, the API re-runs the
# same request on a substitute model inside the same call (routed by refusal category).
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ApiNotConfigured(RuntimeError):
    pass


def key_configured() -> bool:
    return bool(get_settings().anthropic_api_key.strip())


@lru_cache
def _client() -> anthropic.Anthropic:
    s = get_settings()
    # The SDK retries 408/409/429/5xx and connection errors with exponential backoff.
    return anthropic.Anthropic(api_key=s.anthropic_api_key.strip(), timeout=s.api_timeout_s, max_retries=s.api_max_retries)


def get_client() -> anthropic.Anthropic:
    if not key_configured():
        raise ApiNotConfigured("ANTHROPIC_API_KEY is not set in backend/.env")
    return _client()


def fallback_kwargs() -> dict[str, Any]:
    """Extra kwargs for client.beta.messages.* that enable server-side refusal fallbacks."""
    return {"betas": [FALLBACK_BETA], "fallbacks": "default"}


def short_error(exc: BaseException) -> str:
    msg: Optional[str] = getattr(exc, "message", None) or str(exc)
    return f"{type(exc).__name__}: {msg}"[:300]
