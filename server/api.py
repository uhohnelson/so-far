from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from server.database import get_db, init_db
from server.models import WatchStatus
from server.schemas import (
    AddLibraryIn,
    LibraryItemOut,
    MarkWatchedIn,
    ProgressIn,
    SearchResultOut,
    TitleOut,
)
from server import services
from server.tmdb import TmdbClient


def create_app() -> FastAPI:
    tmdb = TmdbClient()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        yield

    app = FastAPI(title="Sofar API", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/search", response_model=list[SearchResultOut])
    def search(q: str = Query(min_length=1), limit: int = Query(default=8, ge=1, le=20)) -> list[SearchResultOut]:
        results = tmdb.search(q, limit=limit)
        return [
            SearchResultOut(
                tmdb_id=r.tmdb_id,
                media_type=r.media_type,
                title=r.title,
                year=r.year,
                overview=r.overview,
                poster_path=r.poster_path,
                poster_url=tmdb.poster_url(r.poster_path),
            )
            for r in results
        ]

    @app.get("/titles/{media_type}/{tmdb_id}", response_model=TitleOut)
    def title_detail(
        media_type: str, tmdb_id: int, db: Session = Depends(get_db)
    ) -> TitleOut:
        if media_type not in {"movie", "tv"}:
            raise HTTPException(status_code=400, detail="media_type must be movie or tv")
        title = services.upsert_title_from_tmdb(db, tmdb, media_type, tmdb_id)
        return TitleOut(
            id=title.id,
            tmdb_id=title.tmdb_id,
            media_type=title.media_type,
            title=title.title,
            year=title.year,
            overview=title.overview,
            poster_path=title.poster_path,
            poster_url=tmdb.poster_url(title.poster_path),
        )

    def _library_out(row) -> LibraryItemOut:
        return LibraryItemOut(
            id=row.id,
            status=row.status,
            current_season=row.current_season,
            current_episode=row.current_episode,
            title=TitleOut(
                id=row.title.id,
                tmdb_id=row.title.tmdb_id,
                media_type=row.title.media_type,
                title=row.title.title,
                year=row.title.year,
                overview=row.title.overview,
                poster_path=row.title.poster_path,
                poster_url=tmdb.poster_url(row.title.poster_path),
            ),
        )

    @app.get("/library", response_model=list[LibraryItemOut])
    def library(
        telegram_id: int,
        status: WatchStatus | None = None,
        limit: int = Query(default=20, ge=1, le=50),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
    ) -> list[LibraryItemOut]:
        user = services.get_or_create_user(db, telegram_id)
        rows = services.list_library(db, user, status=status, limit=limit, offset=offset)
        return [_library_out(r) for r in rows]

    @app.post("/library", response_model=LibraryItemOut)
    def add_library(body: AddLibraryIn, db: Session = Depends(get_db)) -> LibraryItemOut:
        user = services.get_or_create_user(db, body.telegram_id, body.display_name)
        title = services.upsert_title_from_tmdb(db, tmdb, body.media_type.value, body.tmdb_id)
        row = services.add_or_update_library(
            db,
            user,
            title,
            body.status,
            current_season=body.current_season,
            current_episode=body.current_episode,
        )
        # Reload with title
        row = services.get_library_row(db, user, row.id)
        assert row is not None
        return _library_out(row)

    @app.delete("/library/{user_title_id}")
    def remove_library(
        user_title_id: int, telegram_id: int, db: Session = Depends(get_db)
    ) -> dict[str, bool]:
        user = services.get_or_create_user(db, telegram_id)
        ok = services.remove_from_library(db, user, user_title_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Not in library")
        return {"ok": True}

    @app.post("/library/{user_title_id}/progress", response_model=LibraryItemOut)
    def set_progress(
        user_title_id: int, body: ProgressIn, db: Session = Depends(get_db)
    ) -> LibraryItemOut:
        user = services.get_or_create_user(db, body.telegram_id)
        row = services.set_progress(db, user, user_title_id, body.season, body.episode)
        if not row:
            raise HTTPException(status_code=404, detail="TV title not found in library")
        row = services.get_library_row(db, user, row.id)
        assert row is not None
        return _library_out(row)

    @app.post("/library/{user_title_id}/watched")
    def mark_watched(
        user_title_id: int, body: MarkWatchedIn, db: Session = Depends(get_db)
    ) -> dict:
        user = services.get_or_create_user(db, body.telegram_id)
        row, message = services.mark_episode_watched(db, tmdb, user, user_title_id)
        if not row:
            raise HTTPException(status_code=404, detail=message)
        row = services.get_library_row(db, user, row.id)
        assert row is not None
        return {"message": message, "item": _library_out(row)}

    return app


app = create_app()
