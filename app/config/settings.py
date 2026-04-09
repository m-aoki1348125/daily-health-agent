from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    log_level: str = "INFO"
    health_agent_date: str | None = None
    timezone: str = "Asia/Tokyo"

    database_url: str = "sqlite+pysqlite:///./local.db"
    db_echo: bool = False

    fitbit_client_mode: Literal["mock", "api"] = "mock"
    fitbit_base_url: str = "https://api.fitbit.com"
    fitbit_client_id: str | None = None
    fitbit_client_secret: str | None = None
    fitbit_refresh_token: str | None = None
    historical_bootstrap_enabled: bool = True
    historical_bootstrap_days: int = Field(default=90, ge=0, le=365)
    historical_bootstrap_max_days_per_run: int = Field(default=14, ge=1, le=365)

    google_drive_mode: Literal["local", "api"] = "local"
    drive_root_folder_id: str = "HealthAgent"
    drive_local_root: str = ".local_drive"
    drive_oauth_client_id: str | None = None
    drive_oauth_client_secret: str | None = None
    drive_oauth_refresh_token: str | None = None
    drive_oauth_token_uri: str = "https://oauth2.googleapis.com/token"

    line_client_mode: Literal["mock", "api"] = "mock"
    line_channel_access_token: str | None = None
    line_channel_secret: str | None = None
    line_user_id: str = "mock-user"
    line_restrict_to_configured_user: bool = True
    line_webhook_path: str = "/line/webhook"
    line_webhook_port: int = 8080

    llm_provider: Literal["mock", "openai", "claude"] = "mock"
    llm_model_name: str = "gpt-4.1-mini"
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 2
    openai_api_key: str | None = None
    claude_api_key: str | None = None

    sleep_debt_threshold_minutes: int = 390
    sleep_deficit_alert_delta_minutes: int = 60
    resting_hr_elevation_bpm: int = 4
    bedtime_drift_alert_minutes: int = 45
    recovery_score_yellow_threshold: int = 55
    recovery_score_red_threshold: int = 35

    request_timeout_seconds: int = Field(default=30, ge=1)
    meal_calorie_alert_delta: int = 400
    meal_calorie_balance_alert_delta: int = 300


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
