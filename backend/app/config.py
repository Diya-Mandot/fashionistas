from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

ApiMode = Literal["live", "replay", "mock"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "EcoStylist"

    agents_api_key: str = ""
    agents_api_base_url: str = ""
    agents_mode: ApiMode = "live"

    decisions_api_key: str = ""
    decisions_api_base_url: str = ""
    decisions_mode: ApiMode = "live"

    google_vision_api_key: str = ""
    google_application_credentials: str = ""

    database_url: str = f"sqlite:///{BACKEND_DIR / 'ecostylist.db'}"
    frontend_origin: str = "http://localhost:5173"
    dev_endpoints: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
