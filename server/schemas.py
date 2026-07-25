from __future__ import annotations

from pydantic import BaseModel, Field

from server.models import MediaType, WatchStatus


class SearchResultOut(BaseModel):
    tmdb_id: int
    media_type: MediaType
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    poster_url: str | None = None


class TitleOut(BaseModel):
    id: int
    tmdb_id: int
    media_type: MediaType
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    poster_url: str | None = None

    model_config = {"from_attributes": True}


class LibraryItemOut(BaseModel):
    id: int
    status: WatchStatus
    current_season: int | None = None
    current_episode: int | None = None
    title: TitleOut

    model_config = {"from_attributes": True}


class AddLibraryIn(BaseModel):
    telegram_id: int
    display_name: str | None = None
    tmdb_id: int
    media_type: MediaType
    status: WatchStatus
    current_season: int | None = None
    current_episode: int | None = None


class ProgressIn(BaseModel):
    telegram_id: int
    season: int = Field(ge=1)
    episode: int = Field(ge=1)


class TelegramUserIn(BaseModel):
    telegram_id: int
    display_name: str | None = None


class MarkWatchedIn(BaseModel):
    telegram_id: int
