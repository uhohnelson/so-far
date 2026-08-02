from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str
    tmdb_api_key: str
    database_url: str = "sqlite:///./data/sofar.db"
    default_timezone: str = "America/New_York"
    web_app_url: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_image_base: str = "https://image.tmdb.org/t/p/w500"
    # When unset/false, FastAPI /docs /redoc /openapi.json are disabled.
    sofar_debug: bool = False
    # Background episode-alert poll interval (bot job queue, seconds).
    alert_check_interval_sec: int = 3600
    # Alert only for episodes that aired within this many days (inclusive of today).
    # 1 = today + yesterday (covers missed hourly scans / timezone edges).
    alert_lookback_days: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
