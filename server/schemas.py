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
    backdrop_url: str | None = None


class SeasonOut(BaseModel):
    season_number: int
    episode_count: int | None = None
    name: str | None = None
    poster_url: str | None = None
    air_date: str | None = None


class CastOut(BaseModel):
    id: int
    name: str
    character: str | None = None
    profile_url: str | None = None


class ProviderOut(BaseModel):
    name: str
    logo_url: str | None = None


class EpisodeOut(BaseModel):
    season: int
    episode: int
    name: str | None = None
    air_date: str | None = None
    overview: str | None = None
    still_url: str | None = None
    runtime: int | None = None
    watched: bool = False


class TitleOut(BaseModel):
    id: int
    tmdb_id: int
    media_type: MediaType
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    tagline: str | None = None
    genres: list[str] = []
    runtime: int | None = None
    status: str | None = None
    vote_average: float | None = None
    networks: list[str] = []
    number_of_seasons: int | None = None
    number_of_episodes: int | None = None
    seasons: list[SeasonOut] | None = None
    cast: list[CastOut] = []
    release_date: str | None = None
    trailer_url: str | None = None
    providers: list[ProviderOut] = []

    model_config = {"from_attributes": True}


class LibraryItemOut(BaseModel):
    id: int
    status: WatchStatus
    current_season: int | None = None
    current_episode: int | None = None
    title: TitleOut

    model_config = {"from_attributes": True}


class TitleDetailOut(BaseModel):
    """Full title page payload for the web app."""

    title: TitleOut
    library_item: LibraryItemOut | None = None
    watched_episodes: list[str] = []  # "S1E3" keys


class SeasonEpisodesOut(BaseModel):
    season: int
    episodes: list[EpisodeOut]
    previous_unwatched: int = 0  # helper when marking a specific ep later


class AddLibraryIn(BaseModel):
    tmdb_id: int
    media_type: MediaType
    status: WatchStatus = WatchStatus.want
    current_season: int | None = None
    current_episode: int | None = None


class LibraryStatusIn(BaseModel):
    status: WatchStatus


class ProgressIn(BaseModel):
    season: int = Field(ge=1)
    episode: int = Field(ge=1)


class MarkEpisodeIn(BaseModel):
    season: int = Field(ge=1)
    episode: int = Field(ge=1)
    mark_previous: bool = False


class ExchangeCodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=16)


class UserOut(BaseModel):
    id: int
    display_name: str | None = None
    cover_title_id: int | None = None
    cover_url: str | None = None

    model_config = {"from_attributes": True}


class UserUpdateIn(BaseModel):
    cover_title_id: int | None = None


class AuthOut(BaseModel):
    token: str
    user: UserOut


class StatsOut(BaseModel):
    episodes: int
    movies: int
    minutes: int


class PersonOut(BaseModel):
    id: int
    name: str
    biography: str | None = None
    profile_url: str | None = None
    known_for: str | None = None
