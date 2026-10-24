from functools import lru_cache
from typing import Optional

from openai import OpenAI

from app.config import get_settings


class ApiNotConfigured(RuntimeError):
    pass


def key_configured() -> bool:
    return bool(get_settings().openai_api_key.strip())


@lru_cache
def _client() -> OpenAI:
    s = get_settings()
    # The SDK retries 408/409/429/5xx with exponential backoff and honors Retry-After.
    return OpenAI(api_key=s.openai_api_key.strip(), timeout=s.api_timeout_s, max_retries=s.api_max_retries)


def get_client() -> OpenAI:
    if not key_configured():
        raise ApiNotConfigured("OPENAI_API_KEY is not set in backend/.env")
    return _client()


def short_error(exc: BaseException) -> str:
    msg: Optional[str] = getattr(exc, "message", None) or str(exc)
    return f"{type(exc).__name__}: {msg}"[:300]
