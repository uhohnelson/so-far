from __future__ import annotations

from dataclasses import dataclass

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


@dataclass
class TitleDetail:
    tmdb_id: int
    media_type: str
    title: str
    year: int | None
    overview: str | None
    poster_path: str | None
    seasons: list[dict] | None = None


@dataclass
class EpisodeInfo:
    season: int
    episode: int
    name: str | None
    air_date: str | None


class TmdbClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _get(self, path: str, params: dict | None = None) -> dict:
        query = {"api_key": self.settings.tmdb_api_key}
        if params:
            query.update(params)
        with httpx.Client(base_url=self.settings.tmdb_base_url, timeout=20.0) as client:
            response = client.get(path, params=query)
            response.raise_for_status()
            return response.json()

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
        path = f"/trending/{media_type or 'all'}/week"
        data = self._get(path)
        results: list[SearchResult] = []
        for item in data.get("results", []):
            parsed = self._parse_result(item)
            if parsed:
                results.append(parsed)
            if len(results) >= limit:
                break
        return results

    def get_title(self, media_type: str, tmdb_id: int) -> TitleDetail:
        data = self._get(f"/{media_type}/{tmdb_id}")
        title = data.get("title") or data.get("name") or "Untitled"
        date = data.get("release_date") or data.get("first_air_date") or ""
        year = int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None
        overview = data.get("overview") or None
        if overview and len(overview) > 500:
            overview = overview[:497] + "..."
        seasons = None
        if media_type == "tv":
            seasons = [
                {
                    "season_number": s.get("season_number"),
                    "episode_count": s.get("episode_count"),
                    "name": s.get("name"),
                }
                for s in data.get("seasons", [])
                if s.get("season_number", 0) > 0
            ]
        return TitleDetail(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            year=year,
            overview=overview,
            poster_path=data.get("poster_path"),
            seasons=seasons,
        )

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
        )

    def next_episode(
        self, tmdb_id: int, season: int, episode: int, seasons: list[dict] | None = None
    ) -> EpisodeInfo | None:
        # Try next episode in same season
        nxt = self.get_episode(tmdb_id, season, episode + 1)
        if nxt:
            return nxt
        # Try first episode of next season
        if seasons is None:
            detail = self.get_title("tv", tmdb_id)
            seasons = detail.seasons or []
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
