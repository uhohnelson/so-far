from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from server import services
from server.alerts import is_alerts_muted, set_alerts_muted
from server.config import get_settings
from server.database import get_db, init_db
from server.models import Title, User, UserTitle, WatchEvent, WatchStatus
from server.rate_limit import (
    exchange_limiter,
    tmdb_detail_limiter,
    tmdb_feed_limiter,
    tmdb_search_limiter,
    tmdb_season_limiter,
)
from server.schemas import (
    AddLibraryIn,
    AlertPrefIn,
    AlertPrefOut,
    AuthOut,
    CastOut,
    EpisodeOut,
    ExchangeCodeIn,
    LibraryItemOut,
    LibraryStatusIn,
    MarkEpisodeIn,
    PersonOut,
    ProgressIn,
    ProviderOut,
    SearchResultOut,
    SeasonEpisodesOut,
    SeasonOut,
    StatsOut,
    TitleDetailOut,
    TitleOut,
    UserOut,
    UserUpdateIn,
)
from server.tmdb import TmdbClient

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

_bearer = HTTPBearer(auto_error=False)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _tmdb_rate_key(request: Request, user: User) -> str:
    return f"u{user.id}:{_client_ip(request)}"


def _enforce_tmdb_limit(limiter, request: Request, user: User) -> None:
    reason = limiter.check(_tmdb_rate_key(request, user))
    if reason:
        raise HTTPException(status_code=429, detail=reason)


def create_app() -> FastAPI:
    tmdb = TmdbClient()
    settings = get_settings()
    debug = settings.sofar_debug

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        yield
        close = getattr(tmdb, "close", None)
        if callable(close):
            close()

    app = FastAPI(
        title="Sofar API",
        version="0.3.0",
        lifespan=lifespan,
        docs_url="/docs" if debug else None,
        redoc_url="/redoc" if debug else None,
        openapi_url="/openapi.json" if debug else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def current_user(
        creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: Session = Depends(get_db),
    ) -> User:
        if creds is None:
            raise HTTPException(status_code=401, detail="Missing token")
        user = services.get_user_by_token(db, creds.credentials)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user

    def _meta(title: Title) -> dict:
        if not title.cached_metadata:
            return {}
        try:
            return json.loads(title.cached_metadata)
        except json.JSONDecodeError:
            return {}

    def _title_out(title: Title, *, lite: bool = False) -> TitleOut:
        meta = _meta(title)
        seasons_raw = meta.get("seasons") or []
        if lite:
            seasons = [
                SeasonOut(
                    season_number=s["season_number"],
                    episode_count=s.get("episode_count"),
                    name=s.get("name"),
                    poster_url=None,
                    air_date=s.get("air_date"),
                )
                for s in seasons_raw
                if s.get("season_number") is not None
            ] or None
            return TitleOut(
                id=title.id,
                tmdb_id=title.tmdb_id,
                media_type=title.media_type,
                title=title.title,
                year=title.year,
                overview=None,
                poster_path=title.poster_path,
                poster_url=tmdb.poster_url(title.poster_path, size="w185"),
                backdrop_url=None,
                tagline=None,
                genres=[],
                runtime=None,
                status=None,
                vote_average=None,
                networks=[],
                number_of_seasons=meta.get("number_of_seasons"),
                number_of_episodes=None,
                seasons=seasons,
                cast=[],
                release_date=meta.get("release_date"),
                trailer_url=None,
                providers=[],
            )

        seasons = [
            SeasonOut(
                season_number=s["season_number"],
                episode_count=s.get("episode_count"),
                name=s.get("name"),
                poster_url=tmdb.poster_url(s.get("poster_path"), size="w185"),
                air_date=s.get("air_date"),
            )
            for s in seasons_raw
            if s.get("season_number") is not None
        ] or None
        cast = [
            CastOut(
                id=c["id"],
                name=c["name"],
                character=c.get("character"),
                profile_url=tmdb.poster_url(c.get("profile_path"), size="w185"),
            )
            for c in meta.get("cast") or []
        ]
        providers = [
            ProviderOut(
                name=p["name"],
                logo_url=tmdb.poster_url(p.get("logo_path"), size="w92"),
            )
            for p in meta.get("providers") or []
            if p.get("name")
        ]
        trailer_key = meta.get("trailer_key")
        trailer_url = (
            f"https://www.youtube.com/watch?v={trailer_key}" if trailer_key else None
        )
        return TitleOut(
            id=title.id,
            tmdb_id=title.tmdb_id,
            media_type=title.media_type,
            title=title.title,
            year=title.year,
            overview=title.overview,
            poster_path=title.poster_path,
            poster_url=tmdb.poster_url(title.poster_path, size="w342"),
            backdrop_url=tmdb.poster_url(meta.get("backdrop_path"), size="w780"),
            tagline=meta.get("tagline"),
            genres=meta.get("genres") or [],
            runtime=meta.get("runtime"),
            status=meta.get("status"),
            vote_average=meta.get("vote_average"),
            networks=meta.get("networks") or [],
            number_of_seasons=meta.get("number_of_seasons"),
            number_of_episodes=meta.get("number_of_episodes"),
            seasons=seasons,
            cast=cast,
            release_date=meta.get("release_date"),
            trailer_url=trailer_url,
            providers=providers,
        )

    def _search_out(r) -> SearchResultOut:
        return SearchResultOut(
            tmdb_id=r.tmdb_id,
            media_type=r.media_type,
            title=r.title,
            year=r.year,
            overview=r.overview,
            poster_path=r.poster_path,
            poster_url=tmdb.poster_url(r.poster_path),
            backdrop_url=tmdb.poster_url(r.backdrop_path, size="w780"),
        )

    def _watched_count_for(db: Session, user: User, title_id: int) -> int:
        return sum(
            1
            for s, e in services.list_watched_episodes(db, user, title_id)
            if (s, e) != (0, 0)
        )

    def _library_out(row: UserTitle, watched_count: int = 0) -> LibraryItemOut:
        return LibraryItemOut(
            id=row.id,
            status=row.status,
            current_season=row.current_season,
            current_episode=row.current_episode,
            watched_count=watched_count,
            title=_title_out(row.title, lite=True),
        )

    def _find_library(db: Session, user: User, title: Title) -> UserTitle | None:
        return db.scalar(
            select(UserTitle).where(
                UserTitle.user_id == user.id, UserTitle.title_id == title.id
            )
        )

    def _user_out(user: User, db: Session | None = None) -> UserOut:
        cover_url = None
        cover_title = None
        if user.cover_title_id is not None:
            cover_title = user.cover_title
            if cover_title is None and db is not None:
                cover_title = db.get(Title, user.cover_title_id)
        if cover_title is not None:
            meta = _meta(cover_title)
            cover_url = tmdb.poster_url(meta.get("backdrop_path"), size="w780") or tmdb.poster_url(
                cover_title.poster_path, size="w780"
            )
        return UserOut(
            id=user.id,
            display_name=user.display_name,
            cover_title_id=user.cover_title_id,
            cover_url=cover_url,
            timezone=user.timezone,
        )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/exchange", response_model=AuthOut)
    def exchange_code(
        body: ExchangeCodeIn,
        request: Request,
        db: Session = Depends(get_db),
    ) -> AuthOut:
        ip = _client_ip(request)
        limited = exchange_limiter.check(ip)
        if limited:
            raise HTTPException(status_code=429, detail=limited)
        result = services.exchange_login_code(db, body.code)
        if result is None:
            exchange_limiter.record_failure(ip)
            raise HTTPException(
                status_code=401,
                detail="Code is wrong or expired. Get a fresh one from the bot with /app.",
            )
        raw_token, token = result
        return AuthOut(token=raw_token, user=_user_out(token.user, db))

    @app.post("/api/auth/logout")
    def logout(
        creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: Session = Depends(get_db),
    ) -> dict[str, bool]:
        if creds is not None:
            services.revoke_token(db, creds.credentials)
        return {"ok": True}

    @app.get("/api/me", response_model=UserOut)
    def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> UserOut:
        return _user_out(user, db)

    @app.patch("/api/me", response_model=UserOut)
    def update_me(
        body: UserUpdateIn,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> UserOut:
        if "cover_title_id" in body.model_fields_set:
            if body.cover_title_id is None:
                user.cover_title_id = None
            else:
                title = db.get(Title, body.cover_title_id)
                if title is None:
                    raise HTTPException(status_code=404, detail="Title not found.")
                owned = db.scalar(
                    select(UserTitle).where(
                        UserTitle.user_id == user.id,
                        UserTitle.title_id == title.id,
                    )
                )
                if owned is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Pick a cover from something on your list.",
                    )
                user.cover_title_id = title.id
        if "timezone" in body.model_fields_set and body.timezone is not None:
            try:
                services.set_user_timezone(db, user, body.timezone)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        db.commit()
        db.refresh(user)
        return _user_out(user, db)

    @app.get("/api/stats", response_model=StatsOut)
    def stats(
        user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> StatsOut:
        return StatsOut(**services.get_stats(db, user))

    @app.get("/api/search", response_model=list[SearchResultOut])
    def search(
        request: Request,
        q: str = Query(min_length=1),
        media_type: str | None = Query(default=None),
        limit: int = Query(default=12, ge=1, le=20),
        user: User = Depends(current_user),
    ) -> list[SearchResultOut]:
        _enforce_tmdb_limit(tmdb_search_limiter, request, user)
        mt = media_type if media_type in {"movie", "tv"} else None
        return [
            _search_out(r)
            for r in tmdb.search(q, limit=limit, media_type=mt)
        ]

    @app.get("/api/trending", response_model=list[SearchResultOut])
    def trending(
        request: Request,
        media_type: str | None = Query(default=None),
        limit: int = Query(default=12, ge=1, le=20),
        user: User = Depends(current_user),
    ) -> list[SearchResultOut]:
        _enforce_tmdb_limit(tmdb_feed_limiter, request, user)
        mt = media_type if media_type in {"movie", "tv"} else None
        return [_search_out(r) for r in tmdb.trending(limit=limit, media_type=mt)]

    @app.get("/api/top-rated", response_model=list[SearchResultOut])
    def top_rated(
        request: Request,
        media_type: str = Query(pattern="^(movie|tv)$"),
        limit: int = Query(default=12, ge=1, le=20),
        user: User = Depends(current_user),
    ) -> list[SearchResultOut]:
        _enforce_tmdb_limit(tmdb_feed_limiter, request, user)
        return [
            _search_out(r)
            for r in tmdb.top_rated(media_type=media_type, limit=limit)
        ]

    @app.get("/api/person/{person_id}", response_model=PersonOut)
    def person_detail(
        person_id: int,
        user: User = Depends(current_user),
    ) -> PersonOut:
        data = tmdb.get_person(person_id)
        known = data.get("known_for_department")
        return PersonOut(
            id=data["id"],
            name=data.get("name") or "Unknown",
            biography=data.get("biography") or None,
            profile_url=tmdb.poster_url(data.get("profile_path"), size="w342"),
            known_for=known,
        )

    @app.get("/api/person/{person_id}/credits", response_model=list[SearchResultOut])
    def person_credits(
        person_id: int,
        user: User = Depends(current_user),
    ) -> list[SearchResultOut]:
        return [_search_out(r) for r in tmdb.get_person_credits(person_id)]

    @app.get("/api/titles/{media_type}/{tmdb_id}", response_model=TitleDetailOut)
    def title_detail(
        media_type: str,
        tmdb_id: int,
        request: Request,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> TitleDetailOut:
        if media_type not in {"movie", "tv"}:
            raise HTTPException(status_code=400, detail="media_type must be movie or tv")
        _enforce_tmdb_limit(tmdb_detail_limiter, request, user)
        title = services.upsert_title_from_tmdb(db, tmdb, media_type, tmdb_id)
        row = _find_library(db, user, title)
        watched = []
        alerts_muted = None
        if row:
            watched = [
                f"S{s}E{e}"
                for s, e in services.list_watched_episodes(db, user, title.id)
            ]
            if row.status == WatchStatus.watching and title.media_type.value == "tv":
                alerts_muted = is_alerts_muted(db, user.id, title.id)
        return TitleDetailOut(
            title=_title_out(title),
            library_item=_library_out(row, watched_count=len(watched)) if row else None,
            watched_episodes=watched,
            alerts_muted=alerts_muted,
        )

    @app.get(
        "/api/titles/{media_type}/{tmdb_id}/similar",
        response_model=list[SearchResultOut],
    )
    def title_similar(
        media_type: str,
        tmdb_id: int,
        request: Request,
        limit: int = Query(default=12, ge=1, le=20),
        user: User = Depends(current_user),
    ) -> list[SearchResultOut]:
        if media_type not in {"movie", "tv"}:
            raise HTTPException(status_code=400, detail="media_type must be movie or tv")
        _enforce_tmdb_limit(tmdb_feed_limiter, request, user)
        return [
            _search_out(r)
            for r in tmdb.get_recommendations(media_type, tmdb_id, limit=limit)
        ]

    @app.get(
        "/api/titles/tv/{tmdb_id}/season/{season}",
        response_model=SeasonEpisodesOut,
    )
    def season_episodes(
        tmdb_id: int,
        season: int,
        request: Request,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> SeasonEpisodesOut:
        _enforce_tmdb_limit(tmdb_season_limiter, request, user)
        title = services.upsert_title_from_tmdb(db, tmdb, "tv", tmdb_id)
        watched = services.list_watched_episodes(db, user, title.id)
        episodes = []
        for ep in tmdb.get_season_episodes(tmdb_id, season):
            episodes.append(
                EpisodeOut(
                    season=ep.season,
                    episode=ep.episode,
                    name=ep.name,
                    air_date=ep.air_date,
                    overview=ep.overview,
                    still_url=tmdb.poster_url(ep.still_path, size="w300"),
                    runtime=ep.runtime,
                    watched=(ep.season, ep.episode) in watched,
                )
            )
        return SeasonEpisodesOut(season=season, episodes=episodes)

    @app.get("/api/library", response_model=list[LibraryItemOut])
    def library(
        status: WatchStatus | None = None,
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> list[LibraryItemOut]:
        rows = services.list_library(db, user, status=status, limit=limit, offset=offset)
        events = db.scalars(
            select(WatchEvent).where(WatchEvent.user_id == user.id)
        ).all()
        counts: dict[int, int] = {}
        for e in events:
            if e.season == 0 and e.episode == 0:
                continue
            counts[e.title_id] = counts.get(e.title_id, 0) + 1
        return [
            _library_out(r, watched_count=counts.get(r.title_id, 0)) for r in rows
        ]

    @app.post("/api/library", response_model=LibraryItemOut)
    def add_library(
        body: AddLibraryIn,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> LibraryItemOut:
        title = services.upsert_title_from_tmdb(db, tmdb, body.media_type.value, body.tmdb_id)
        row = services.add_or_update_library(
            db,
            user,
            title,
            body.status,
            current_season=body.current_season,
            current_episode=body.current_episode,
        )
        row = services.get_library_row(db, user, row.id)
        assert row is not None
        return _library_out(row, watched_count=_watched_count_for(db, user, row.title_id))

    @app.patch("/api/library/{user_title_id}/alerts", response_model=AlertPrefOut)
    def update_alert_pref(
        user_title_id: int,
        body: AlertPrefIn,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> AlertPrefOut:
        row = services.get_library_row(db, user, user_title_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not in library")
        if row.title.media_type.value != "tv" or row.status != WatchStatus.watching:
            raise HTTPException(
                status_code=400,
                detail="Alerts apply to shows you are watching.",
            )
        set_alerts_muted(db, user, row.title_id, body.muted)
        return AlertPrefOut(muted=body.muted)

    @app.patch("/api/library/{user_title_id}", response_model=LibraryItemOut)
    def update_library_status(
        user_title_id: int,
        body: LibraryStatusIn,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> LibraryItemOut:
        row = services.set_library_status(db, user, user_title_id, body.status)
        if not row:
            raise HTTPException(status_code=404, detail="Not in library")
        row = services.get_library_row(db, user, row.id)
        assert row is not None
        return _library_out(row, watched_count=_watched_count_for(db, user, row.title_id))

    @app.delete("/api/library/{user_title_id}")
    def remove_library(
        user_title_id: int,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> dict[str, bool]:
        ok = services.remove_from_library(db, user, user_title_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Not in library")
        return {"ok": True}

    @app.post("/api/library/{user_title_id}/progress", response_model=LibraryItemOut)
    def set_progress(
        user_title_id: int,
        body: ProgressIn,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> LibraryItemOut:
        row = services.set_progress(db, user, user_title_id, body.season, body.episode)
        if not row:
            raise HTTPException(status_code=404, detail="TV title not found in library")
        row = services.get_library_row(db, user, row.id)
        assert row is not None
        return _library_out(row, watched_count=_watched_count_for(db, user, row.title_id))

    @app.post("/api/library/{user_title_id}/watched")
    def mark_watched(
        user_title_id: int,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        row, message = services.mark_episode_watched(db, tmdb, user, user_title_id)
        if not row:
            raise HTTPException(status_code=404, detail=message)
        row = services.get_library_row(db, user, row.id)
        assert row is not None
        return {"message": message, "item": _library_out(row, watched_count=_watched_count_for(db, user, row.title_id)).model_dump()}

    @app.post("/api/library/{user_title_id}/episodes")
    def mark_episode(
        user_title_id: int,
        body: MarkEpisodeIn,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        row = services.get_library_row(db, user, user_title_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not in library")

        # Count how many earlier episodes are still unmarked (for the dialog).
        watched = services.list_watched_episodes(db, user, row.title_id)
        prev = services.previous_episodes(row.title, body.season, body.episode)
        previous_unwatched = sum(1 for p in prev if p not in watched)

        # If client only asked for a preview count:
        # (handled client-side usually; we still return it on every mark)

        updated, message, previous_marked = services.mark_specific_episode(
            db,
            tmdb,
            user,
            user_title_id,
            body.season,
            body.episode,
            mark_previous=body.mark_previous,
        )
        if not updated:
            raise HTTPException(status_code=404, detail=message)
        updated = services.get_library_row(db, user, updated.id)
        assert updated is not None
        return {
            "message": message,
            "item": _library_out(updated, watched_count=_watched_count_for(db, user, updated.title_id)).model_dump(),
            "previous_unwatched": previous_unwatched,
            "previous_marked": previous_marked,
        }

    @app.delete("/api/library/{user_title_id}/episodes/{season}/{episode}")
    def unmark_episode(
        user_title_id: int,
        season: int,
        episode: int,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        row = services.unmark_specific_episode(db, user, user_title_id, season, episode)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        row = services.get_library_row(db, user, row.id)
        assert row is not None
        return {"item": _library_out(row, watched_count=_watched_count_for(db, user, row.title_id)).model_dump()}

    @app.post("/api/library/{user_title_id}/seasons/all")
    def mark_all_seasons(
        user_title_id: int,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        updated, message = services.mark_all_episodes(db, user, user_title_id)
        if not updated:
            raise HTTPException(status_code=404, detail=message)
        updated = services.get_library_row(db, user, updated.id)
        assert updated is not None
        return {"message": message, "item": _library_out(updated, watched_count=_watched_count_for(db, user, updated.title_id)).model_dump()}

    @app.post("/api/library/{user_title_id}/seasons/{season}")
    def mark_season(
        user_title_id: int,
        season: int,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        updated, message = services.mark_season(
            db, tmdb, user, user_title_id, season
        )
        if not updated:
            raise HTTPException(status_code=404, detail=message)
        updated = services.get_library_row(db, user, updated.id)
        assert updated is not None
        return {"message": message, "item": _library_out(updated, watched_count=_watched_count_for(db, user, updated.title_id)).model_dump()}

    @app.delete("/api/library/{user_title_id}/seasons/{season}")
    def unmark_season(
        user_title_id: int,
        season: int,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        row = services.unmark_season(db, user, user_title_id, season)
        if not row:
            raise HTTPException(status_code=404, detail="Not in library")
        row = services.get_library_row(db, user, row.id)
        assert row is not None
        return {"item": _library_out(row, watched_count=_watched_count_for(db, user, row.title_id)).model_dump()}

    @app.get("/api/library/{user_title_id}/episodes/preview")
    def preview_mark(
        user_title_id: int,
        season: int = Query(ge=1),
        episode: int = Query(ge=1),
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> dict[str, int]:
        row = services.get_library_row(db, user, user_title_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not in library")
        watched = services.list_watched_episodes(db, user, row.title_id)
        prev = services.previous_episodes(row.title, season, episode)
        return {"previous_unwatched": sum(1 for p in prev if p not in watched)}

    if WEB_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str, request: Request) -> FileResponse:
            if path in {"docs", "redoc", "openapi.json"}:
                raise HTTPException(status_code=404, detail="Not found")
            candidate = (WEB_DIST / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(WEB_DIST):
                return FileResponse(candidate)
            return FileResponse(WEB_DIST / "index.html")

    return app


app = create_app()
