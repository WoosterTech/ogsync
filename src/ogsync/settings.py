"""
Centralized application settings.

Uses pydantic-settings to load environment variables and .env file.
Controls things like DEBUG mode and logging defaults.

Additional settings can be added as needed.
"""

import logging
from functools import cached_property
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config: SettingsConfigDict = SettingsConfigDict(  # pyright: ignore[reportIncompatibleVariableOverride]
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="OGSYNC_",
        extra="ignore",
    )

    google_calendar_id: str
    default_sync_window_days: int = 90
    google_client_secret_path: Path = Path("client_secret.json")
    google_token_path: Path = Path("token.json")

    state_db_path: Path = Path("ogsync_state.db")

    debug: bool = False
    log_level: str | None = None

    default_time_zone: str = "UTC"

    default_sync_category: str = "GCal Sync"

    @property
    def default_log_level(self) -> int:
        if self.debug:
            return logging.DEBUG
        return logging.INFO

    @cached_property
    def zoneinfo(self) -> ZoneInfo:
        return ZoneInfo(self.default_time_zone)


settings = Settings()  # pyright: ignore[reportCallIssue]
