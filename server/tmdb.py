from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from server.config import Settings, get_settings


@dataclass
class SearchResult:
    tmdb_id: int
    media_type: str
    title: str
    year: int | None
    overview: str | None
    poster_path: str | None
    backdrop_path: str | None = None


@dataclass
class CastMember:
    id: int
    name: str
    character: str | None
    profile_path: str | None
    order: int = 0


@dataclass
class SeasonSummary:
    season_number: int
    episode_count: int | None
    name: str | None
    poster_path: str | None = None
    air_date: str | None = None
    overview: str | None = None


@dataclass
class EpisodeInfo:
    season: int
    episode: int
    name: str | None
    air_date: str | None
    overview: str | None = None
    still_path: str | None = None
    runtime: int | None = None


@dataclass
class TitleDetail:
    tmdb_id: int
    media_type: str
    title: str
    year: int | None
    overview: str | None
    poster_path: str | None
    backdrop_path: str | None = None
    tagline: str | None = None
    genres: list[str] = field(default_factory=list)
    runtime: int | None = None  # movie minutes, or typical episode minutes for TV
    status: str | None = None
    vote_average: float | None = None
    vote_count: int | None = None
    networks: list[str] = field(default_factory=list)
    number_of_seasons: int | None = None
    number_of_episodes: int | None = None
    seasons: list[SeasonSummary] = field(default_factory=list)
    cast: list[CastMember] = field(default_factory=list)
    release_date: str | None = None
    trailer_key: str | None = None  # YouTube video key
    providers: list[dict] = field(default_factory=list)  # {name, logo_path}


_LIST_CACHE_TTL_SEC = 30 * 60


class TmdbClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._season_cache: dict[tuple[int, int], list[EpisodeInfo]] = {}
        self._list_cache: dict[tuple, tuple[float, list[SearchResult]]] = {}
        self._client = httpx.Client(
            base_url=self.settings.tmdb_base_url, timeout=20.0
        )

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict | None = None) -> dict:
        query = {"api_key": self.settings.tmdb_api_key}
        if params:
            query.update(params)
        response = self._client.get(path, params=query)
        response.raise_for_status()
        return response.json()

    def _list_cache_get(self, key: tuple) -> list[SearchResult] | None:
        hit = self._list_cache.get(key)
        if hit is None:
            return None
        expires_at, results = hit
        if time.monotonic() >= expires_at:
            self._list_cache.pop(key, None)
            return None
        return results

    def _list_cache_set(self, key: tuple, results: list[SearchResult]) -> None:
        self._list_cache[key] = (time.monotonic() + _LIST_CACHE_TTL_SEC, results)

    def _parse_result(self, item: dict, media_type: str | None = None) -> SearchResult | None:
        mt = media_type or item.get("media_type")
        if mt not in {"movie", "tv"}:
            return None
        title = item.get("title") or item.get("name") or "Untitled"
        date = item.get("release_date") or item.get("first_air_date") or ""
        year = int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None
        overview = item.get("overview") or None
        if overview and len(overview) > 280:
            overview = overview[:277] + "..."
        return SearchResult(
            tmdb_id=item["id"],
            media_type=mt,
            title=title,
            year=year,
            overview=overview,
            poster_path=item.get("poster_path"),
            backdrop_path=item.get("backdrop_path"),
        )

    def search(
        self, query: str, limit: int = 8, media_type: str | None = None
    ) -> list[SearchResult]:
        if media_type in {"movie", "tv"}:
            data = self._get(f"/search/{media_type}", {"query": query, "include_adult": "false"})
            results: list[SearchResult] = []
            for item in data.get("results", []):
                parsed = self._parse_result(item, media_type=media_type)
                if parsed:
                    results.append(parsed)
                if len(results) >= limit:
                    break
            return results

        data = self._get("/search/multi", {"query": query, "include_adult": "false"})
        results = []
        for item in data.get("results", []):
            parsed = self._parse_result(item)
            if parsed:
                results.append(parsed)
            if len(results) >= limit:
                break
        return results

    def trending(self, limit: int = 8, media_type: str | None = None) -> list[SearchResult]:
        cache_key = ("trending", media_type or "all", limit)
        cached = self._list_cache_get(cache_key)
        if cached is not None:
            return cached
        path = f"/trending/{media_type or 'all'}/week"
        data = self._get(path)
        results: list[SearchResult] = []
        for item in data.get("results", []):
            parsed = self._parse_result(item)
            if parsed:
                results.append(parsed)
            if len(results) >= limit:
                break
        self._list_cache_set(cache_key, results)
        return results

    def get_recommendations(
        self, media_type: str, tmdb_id: int, limit: int = 12
    ) -> list[SearchResult]:
        if media_type not in {"movie", "tv"}:
            raise ValueError("media_type must be movie or tv")
        cache_key = ("recommendations", media_type, tmdb_id, limit)
        cached = self._list_cache_get(cache_key)
        if cached is not None:
            return cached
        data = self._get(f"/{media_type}/{tmdb_id}/recommendations")
        results: list[SearchResult] = []
        for item in data.get("results", []):
            if item.get("id") == tmdb_id:
                continue
            item["media_type"] = media_type
            parsed = self._parse_result(item)
            if parsed:
                results.append(parsed)
            if len(results) >= limit:
                break
        self._list_cache_set(cache_key, results)
        return results

    def top_rated(self, media_type: str, limit: int = 8) -> list[SearchResult]:
        if media_type not in {"movie", "tv"}:
            raise ValueError("media_type must be movie or tv")
        cache_key = ("top_rated", media_type, limit)
        cached = self._list_cache_get(cache_key)
        if cached is not None:
            return cached
        data = self._get(f"/{media_type}/top_rated")
        results: list[SearchResult] = []
        for item in data.get("results", []):
            item["media_type"] = media_type
            parsed = self._parse_result(item)
            if parsed:
                results.append(parsed)
            if len(results) >= limit:
                break
        self._list_cache_set(cache_key, results)
        return results

    def _parse_cast(self, credits: dict | None, limit: int = 16) -> list[CastMember]:
        if not credits:
            return []
        cast: list[CastMember] = []
        for c in credits.get("cast", [])[:limit]:
            cast.append(
                CastMember(
                    id=c["id"],
                    name=c.get("name") or "Unknown",
                    character=c.get("character") or None,
                    profile_path=c.get("profile_path"),
                    order=c.get("order", 0),
                )
            )
        return cast

    def _parse_trailer(self, data: dict) -> str | None:
        best = None
        for v in (data.get("videos") or {}).get("results", []):
            if v.get("site") != "YouTube" or not v.get("key"):
                continue
            if v.get("type") == "Trailer":
                return v["key"]
            if best is None and v.get("type") == "Teaser":
                best = v["key"]
        return best

    def _parse_providers(self, data: dict, region: str = "US") -> list[dict]:
        results = (data.get("watch/providers") or {}).get("results") or {}
        regional = results.get(region) or {}
        providers: list[dict] = []
        seen: set[str] = set()
        for group in ("flatrate", "free", "ads"):
            for p in regional.get(group) or []:
                name = p.get("provider_name")
                if name and name not in seen:
                    seen.add(name)
                    providers.append({"name": name, "logo_path": p.get("logo_path")})
        return providers[:8]

    def get_title(self, media_type: str, tmdb_id: int) -> TitleDetail:
        data = self._get(
            f"/{media_type}/{tmdb_id}",
            {"append_to_response": "credits,videos,watch/providers"},
        )
        title = data.get("title") or data.get("name") or "Untitled"
        date = data.get("release_date") or data.get("first_air_date") or ""
        year = int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None
        overview = data.get("overview") or None
        genres = [g.get("name") for g in data.get("genres", []) if g.get("name")]
        cast = self._parse_cast(data.get("credits"))

        seasons: list[SeasonSummary] = []
        runtime = None
        networks: list[str] = []
        number_of_seasons = None
        number_of_episodes = None

        if media_type == "movie":
            runtime = data.get("runtime") or None
        else:
            runtimes = data.get("episode_run_time") or []
            runtime = runtimes[0] if runtimes else None
            networks = [n.get("name") for n in data.get("networks", []) if n.get("name")]
            number_of_seasons = data.get("number_of_seasons")
            number_of_episodes = data.get("number_of_episodes")
            for s in data.get("seasons", []):
                sn = s.get("season_number", 0)
                if sn and sn > 0:
                    seasons.append(
                        SeasonSummary(
                            season_number=sn,
                            episode_count=s.get("episode_count"),
                            name=s.get("name"),
                            poster_path=s.get("poster_path"),
                            air_date=s.get("air_date"),
                            overview=s.get("overview") or None,
                        )
                    )

        return TitleDetail(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            year=year,
            overview=overview,
            poster_path=data.get("poster_path"),
            backdrop_path=data.get("backdrop_path"),
            tagline=data.get("tagline") or None,
            genres=genres,
            runtime=runtime,
            status=data.get("status"),
            vote_average=data.get("vote_average"),
            vote_count=data.get("vote_count"),
            networks=networks,
            number_of_seasons=number_of_seasons,
            number_of_episodes=number_of_episodes,
            seasons=seasons,
            cast=cast,
            release_date=date or None,
            trailer_key=self._parse_trailer(data),
            providers=self._parse_providers(data),
        )

    def get_season_episodes(self, tmdb_id: int, season: int) -> list[EpisodeInfo]:
        cache_key = (tmdb_id, season)
        hit = self._season_cache.get(cache_key)
        if hit is not None:
            return hit
        try:
            data = self._get(f"/tv/{tmdb_id}/season/{season}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                self._season_cache[cache_key] = []
                return []
            raise
        episodes: list[EpisodeInfo] = []
        for ep in data.get("episodes", []):
            episodes.append(
                EpisodeInfo(
                    season=season,
                    episode=ep.get("episode_number") or 0,
                    name=ep.get("name"),
                    air_date=ep.get("air_date"),
                    overview=ep.get("overview") or None,
                    still_path=ep.get("still_path"),
                    runtime=ep.get("runtime"),
                )
            )
        result = [e for e in episodes if e.episode > 0]
        self._season_cache[cache_key] = result
        return result

    def get_episode(self, tmdb_id: int, season: int, episode: int) -> EpisodeInfo | None:
        try:
            data = self._get(f"/tv/{tmdb_id}/season/{season}/episode/{episode}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return EpisodeInfo(
            season=season,
            episode=episode,
            name=data.get("name"),
            air_date=data.get("air_date"),
            overview=data.get("overview") or None,
            still_path=data.get("still_path"),
            runtime=data.get("runtime"),
        )

    def next_episode(
        self, tmdb_id: int, season: int, episode: int, seasons: list[dict] | None = None
    ) -> EpisodeInfo | None:
        nxt = self.get_episode(tmdb_id, season, episode + 1)
        if nxt:
            return nxt
        if seasons is None:
            detail = self.get_title("tv", tmdb_id)
            seasons = [
                {"season_number": s.season_number, "episode_count": s.episode_count}
                for s in detail.seasons
            ]
        season_numbers = sorted(
            s["season_number"] for s in seasons if s.get("season_number") is not None
        )
        for sn in season_numbers:
            if sn > season:
                return self.get_episode(tmdb_id, sn, 1)
        return None

    def poster_url(self, poster_path: str | None, size: str = "w500") -> str | None:
        if not poster_path:
            return None
        return f"https://image.tmdb.org/t/p/{size}{poster_path}"

    def get_person(self, person_id: int) -> dict:
        return self._get(f"/person/{person_id}")

    def get_person_credits(self, person_id: int) -> list[SearchResult]:
        cache_key = ("person_credits", person_id)
        cached = self._list_cache_get(cache_key)
        if cached is not None:
            return cached
        data = self._get(f"/person/{person_id}/combined_credits")
        results: list[SearchResult] = []
        for item in data.get("cast") or []:
            mt = item.get("media_type")
            if mt not in {"movie", "tv"}:
                continue
            parsed = self._parse_result(item, media_type=mt)
            if parsed:
                results.append(parsed)
        results.sort(
            key=lambda r: r.year or 0,
            reverse=True,
        )
        self._list_cache_set(cache_key, results)
        return results
