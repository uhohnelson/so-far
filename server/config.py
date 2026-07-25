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
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_image_base: str = "https://image.tmdb.org/t/p/w500"


@lru_cache
def get_settings() -> Settings:
    return Settings()
