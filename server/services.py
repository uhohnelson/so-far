from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from server.models import MediaType, Title, User, UserTitle, WatchStatus
from server.tmdb import TmdbClient


def get_or_create_user(
    db: Session, telegram_id: int, display_name: str | None = None
) -> User:
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user:
        if display_name and user.display_name != display_name:
            user.display_name = display_name
            db.commit()
            db.refresh(user)
        return user
    user = User(telegram_id=telegram_id, display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def upsert_title_from_tmdb(
    db: Session, tmdb: TmdbClient, media_type: str, tmdb_id: int
) -> Title:
    detail = tmdb.get_title(media_type, tmdb_id)
    mt = MediaType(media_type)
    title = db.scalar(
        select(Title).where(Title.tmdb_id == tmdb_id, Title.media_type == mt)
    )
    cached = json.dumps({"seasons": detail.seasons} if detail.seasons else {})
    if title:
        title.title = detail.title
        title.year = detail.year
        title.poster_path = detail.poster_path
        title.overview = detail.overview
        title.cached_metadata = cached
    else:
        title = Title(
            tmdb_id=tmdb_id,
            media_type=mt,
            title=detail.title,
            year=detail.year,
            poster_path=detail.poster_path,
            overview=detail.overview,
            cached_metadata=cached,
        )
        db.add(title)
    db.commit()
    db.refresh(title)
    return title


def add_or_update_library(
    db: Session,
    user: User,
    title: Title,
    status: WatchStatus,
    current_season: int | None = None,
    current_episode: int | None = None,
) -> UserTitle:
    row = db.scalar(
        select(UserTitle).where(UserTitle.user_id == user.id, UserTitle.title_id == title.id)
    )
    if status == WatchStatus.watching and title.media_type == MediaType.tv:
        current_season = current_season or 1
        current_episode = current_episode or 1
    else:
        current_season = None
        current_episode = None

    if row:
        row.status = status
        row.current_season = current_season
        row.current_episode = current_episode
    else:
        row = UserTitle(
            user_id=user.id,
            title_id=title.id,
            status=status,
            current_season=current_season,
            current_episode=current_episode,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_library(
    db: Session,
    user: User,
    status: WatchStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[UserTitle]:
    stmt = (
        select(UserTitle)
        .options(joinedload(UserTitle.title))
        .where(UserTitle.user_id == user.id)
        .order_by(UserTitle.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(UserTitle.status == status)
    return list(db.scalars(stmt).unique().all())


def get_library_row(db: Session, user: User, user_title_id: int) -> UserTitle | None:
    return db.scalar(
        select(UserTitle)
        .options(joinedload(UserTitle.title))
        .where(UserTitle.id == user_title_id, UserTitle.user_id == user.id)
    )


def remove_from_library(db: Session, user: User, user_title_id: int) -> bool:
    row = get_library_row(db, user, user_title_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def set_progress(
    db: Session, user: User, user_title_id: int, season: int, episode: int
) -> UserTitle | None:
    row = get_library_row(db, user, user_title_id)
    if not row or row.title.media_type != MediaType.tv:
        return None
    row.status = WatchStatus.watching
    row.current_season = season
    row.current_episode = episode
    db.commit()
    db.refresh(row)
    return row


def mark_episode_watched(
    db: Session, tmdb: TmdbClient, user: User, user_title_id: int
) -> tuple[UserTitle | None, str]:
    """Mark current episode done and advance. Returns (row, message)."""
    row = get_library_row(db, user, user_title_id)
    if not row:
        return None, "Title not found in your list."
    if row.title.media_type == MediaType.movie:
        row.status = WatchStatus.watched
        db.commit()
        db.refresh(row)
        return row, f"Marked {row.title.title} as watched."

    season = row.current_season or 1
    episode = row.current_episode or 1
    marked = f"S{season}E{episode}"

    seasons = None
    if row.title.cached_metadata:
        try:
            seasons = json.loads(row.title.cached_metadata).get("seasons")
        except json.JSONDecodeError:
            seasons = None

    nxt = tmdb.next_episode(row.title.tmdb_id, season, episode, seasons)
    if nxt:
        ep_name = f" - {nxt.name}" if nxt.name else ""
        row.current_season = nxt.season
        row.current_episode = nxt.episode
        row.status = WatchStatus.watching
        db.commit()
        db.refresh(row)
        return (
            row,
            f"Marked {marked}. Next up: S{nxt.season}E{nxt.episode}{ep_name}",
        )

    row.status = WatchStatus.watched
    row.current_season = None
    row.current_episode = None
    db.commit()
    db.refresh(row)
    return row, f"Marked {marked}. That was the last known episode - show marked watched."
