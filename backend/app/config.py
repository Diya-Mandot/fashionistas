from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

ApiMode = Literal["live", "replay", "mock"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "EcoStylist"

    # The Agents SDK and Decisions API share one key. Never include it in reprs.
    openai_api_key: str = Field(default="", repr=False)
    agents_model: str = "gpt-6-astra"
    decisions_model: str = "gpt-6-luna"
    agents_mode: ApiMode = "live"
    decisions_mode: ApiMode = "live"
    api_timeout_seconds: float = Field(default=30, gt=0, le=120)
    api_max_retries: int = Field(default=2, ge=0, le=4)
    agent_timeout_seconds: float = Field(default=90, gt=0, le=300)
    agent_max_turns: int = Field(default=10, ge=1, le=30)
    api_recordings_path: Path = BACKEND_DIR / "logs" / "api_calls.jsonl"

    google_vision_api_key: str = ""
    google_application_credentials: str = ""

    database_url: str = f"sqlite:///{BACKEND_DIR / 'ecostylist.db'}"
    frontend_origin: str = "http://localhost:5173"
    dev_endpoints: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
