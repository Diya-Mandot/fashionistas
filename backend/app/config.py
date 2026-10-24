from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

ApiMode = Literal["live", "replay", "mock"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "EcoStylist"

    # One OpenAI key powers both the Agents API and the Decisions API.
    openai_api_key: str = ""
    agents_model: str = "gpt-6-astra"
    decisions_model: str = "gpt-6-luna"
    agents_mode: ApiMode = "live"
    decisions_mode: ApiMode = "live"

    api_timeout_s: float = 45.0
    api_max_retries: int = 3

    google_vision_api_key: str = ""
    vision_timeout_s: float = 12.0
    scan_max_image_bytes: int = 15 * 1024 * 1024
    scan_max_image_pixels: int = 50_000_000
    google_application_credentials: str = ""

    database_url: str = f"sqlite:///{BACKEND_DIR / 'ecostylist.db'}"
    frontend_origin: str = "http://localhost:5173"
    dev_endpoints: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
