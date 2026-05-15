from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Anpanman Scarcity Monitor"
    env: str = "development"
    database_url: str = "sqlite:///./local.db"
    monitor_interval_seconds: int = 300
    enable_background_monitor: bool = True
    http_timeout_seconds: int = 15
    http_user_agent: str = "AnpanmanScarcityMonitor/0.1 (+public-page-monitor)"
    feishu_webhook_url: str = ""
    alert_min_gross_margin_percent: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
