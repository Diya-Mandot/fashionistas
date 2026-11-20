from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

ApiMode = Literal["live", "replay", "mock"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "Fashionistas"

    # One Anthropic key powers both the stylist agent loop and the scoring/classification calls.
    anthropic_api_key: str = ""
    agents_model: str = "claude-opus-5-5"
    decisions_model: str = "claude-opus-5-5"
    # Claude effort (low | medium | high | xhigh | max). Low keeps the agent loop snappy.
    agents_effort: str = "low"
    decisions_effort: str = "low"
    agents_mode: ApiMode = "live"
    decisions_mode: ApiMode = "live"

    api_timeout_s: float = 90.0
    api_max_retries: int = 3

    google_vision_api_key: str = ""
    vision_timeout_s: float = 12.0
    scan_max_image_bytes: int = 15 * 1024 * 1024
    scan_max_image_pixels: int = 50_000_000
    google_application_credentials: str = ""

    # Shop catalog: "thrift" = live Utah thrift-store inventory (catalog/thrift.json, refreshed by
    # scripts/sync_thrift.py; falls back to mock until the first sync), "mock" = the demo partner catalog.
    catalog_source: Literal["thrift", "mock"] = "thrift"

    home_city: str = "San Francisco"
    # Real calendar: a private iCal (.ics) URL or file path. Google Calendar:
    # Settings -> your calendar -> "Secret address in iCal format".
    calendar_ics_url: str = ""
    # Google Calendar sync (OAuth). Create a "Web application" OAuth client in Google Cloud
    # Console and register google_oauth_redirect_uri as an authorized redirect URI.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/api/calendar/google/callback"
    # Which calendars to read: "primary", comma-separated calendar IDs, or "all" (every
    # calendar ticked in your Google Calendar sidebar).
    google_calendar_ids: str = "primary"
    # Where runtime state lives (database, uploads, recordings, logs, Google token). Defaults
    # to backend/. On Railway, set DATA_DIR to the volume's mount path (e.g. /data) so state
    # survives redeploys. An explicit UPLOADS_DIR / DATABASE_URL / RECORDINGS_DIR / LOGS_DIR /
    # GOOGLE_TOKEN_FILE still wins.
    data_dir: str = ""
    uploads_dir: str = ""
    database_url: str = ""
    recordings_dir: str = ""
    logs_dir: str = ""
    google_token_file: str = ""
    frontend_origin: str = "http://localhost:5173"
    dev_endpoints: bool = True

    def model_post_init(self, _context: object) -> None:
        base = Path(self.data_dir) if self.data_dir else BACKEND_DIR
        self.uploads_dir = self.uploads_dir or str(base / "uploads")
        self.database_url = self.database_url or f"sqlite:///{base / 'ecostylist.db'}"
        self.recordings_dir = self.recordings_dir or str(base / "recordings")
        self.logs_dir = self.logs_dir or str(base / "logs")
        self.google_token_file = self.google_token_file or str(
            base / "private_calendar" / "google_token.json"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
