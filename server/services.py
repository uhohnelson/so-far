from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from server.models import (
    ApiToken,
    LoginCode,
    MediaType,
    Title,
    User,
    UserTitle,
    WatchEvent,
    WatchStatus,
)
from server.tmdb import TmdbClient

LOGIN_CODE_TTL = timedelta(minutes=10)
API_TOKEN_TTL = timedelta(days=90)
TITLE_CACHE_TTL = timedelta(hours=48)
LAST_USED_THROTTLE = timedelta(minutes=30)
# No confusable characters (0/O, 1/I/L).
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def create_login_code(db: Session, user: User) -> LoginCode:
    """Issue a fresh 6-char login code, replacing any older ones for this user."""
    db.execute(delete(LoginCode).where(LoginCode.user_id == user.id))
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
    row = LoginCode(user_id=user.id, code=code, expires_at=_utcnow() + LOGIN_CODE_TTL)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def exchange_login_code(db: Session, code: str) -> tuple[str, ApiToken] | None:
    """Trade a valid login code for a long-lived API token.

    Consumes the code atomically (DELETE … RETURNING). Returns
    ``(raw_bearer_token, ApiToken)`` — only the hash is stored.
    """
    normalized = code.strip().upper()
    now = _utcnow()
    # Single-consume: first DELETE wins under SQLite's write lock.
    consumed = db.execute(
        delete(LoginCode)
        .where(LoginCode.code == normalized)
        .returning(LoginCode.user_id, LoginCode.expires_at)
    ).one_or_none()
    if consumed is None:
        db.commit()
        return None
    user_id, expires_at = consumed
    if _as_utc(expires_at) < now:
        db.commit()
        return None

    raw = secrets.token_urlsafe(32)
    token = ApiToken(
        user_id=user_id,
        token=_hash_token(raw),
        expires_at=now + API_TOKEN_TTL,
    )
    db.add(token)
    db.commit()
    token = db.scalar(
        select(ApiToken).options(joinedload(ApiToken.user)).where(ApiToken.id == token.id)
    )
    assert token is not None
    return raw, token


def get_user_by_token(db: Session, token: str) -> User | None:
    digest = _hash_token(token)
    row = db.scalar(
        select(ApiToken)
        .options(joinedload(ApiToken.user))
        .where(ApiToken.token == digest)
    )
    if not row:
        return None
    now = _utcnow()
    if _as_utc(row.expires_at) < now:
        db.delete(row)
        db.commit()
        return None
    last = row.last_used_at
    if last is not None:
        last = _as_utc(last)
    if last is None or now - last >= LAST_USED_THROTTLE:
        row.last_used_at = now
        db.commit()
    return row.user


def revoke_token(db: Session, token: str) -> None:
    db.execute(delete(ApiToken).where(ApiToken.token == _hash_token(token)))
    db.commit()


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
    mt = MediaType(media_type)
    title = db.scalar(
        select(Title).where(Title.tmdb_id == tmdb_id, Title.media_type == mt)
    )
    if title and title.cached_metadata:
        updated = title.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if _utcnow() - updated < TITLE_CACHE_TTL:
            return title

    detail = tmdb.get_title(media_type, tmdb_id)
    seasons_payload = [
        {
            "season_number": s.season_number,
            "episode_count": s.episode_count,
            "name": s.name,
            "poster_path": s.poster_path,
            "air_date": s.air_date,
        }
        for s in detail.seasons
    ]
    cached = json.dumps(
        {
            "seasons": seasons_payload,
            "backdrop_path": detail.backdrop_path,
            "genres": detail.genres,
            "tagline": detail.tagline,
            "runtime": detail.runtime,
            "status": detail.status,
            "vote_average": detail.vote_average,
            "networks": detail.networks,
            "number_of_seasons": detail.number_of_seasons,
            "number_of_episodes": detail.number_of_episodes,
            "release_date": detail.release_date,
            "trailer_key": detail.trailer_key,
            "providers": detail.providers,
            "cast": [
                {
                    "id": c.id,
                    "name": c.name,
                    "character": c.character,
                    "profile_path": c.profile_path,
                }
                for c in detail.cast
            ],
        }
    )
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
    # New movies should not land as watched from a plain add — only via mark_watched.
    if (
        row is None
        and title.media_type == MediaType.movie
        and status == WatchStatus.watched
    ):
        status = WatchStatus.watching
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


def set_library_status(
    db: Session, user: User, user_title_id: int, status: WatchStatus
) -> UserTitle | None:
    row = get_library_row(db, user, user_title_id)
    if not row:
        return None
    title = row.title
    current_season = row.current_season
    current_episode = row.current_episode
    if status == WatchStatus.watching and title.media_type == MediaType.tv:
        current_season = current_season or 1
        current_episode = current_episode or 1
    else:
        current_season = None
        current_episode = None
    row.status = status
    row.current_season = current_season
    row.current_episode = current_episode
    db.commit()
    db.refresh(row)
    return row


def remove_from_library(db: Session, user: User, user_title_id: int) -> bool:
    row = get_library_row(db, user, user_title_id)
    if not row:
        return False
    db.execute(
        delete(WatchEvent).where(
            WatchEvent.user_id == user.id, WatchEvent.title_id == row.title_id
        )
    )
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


def list_watched_episodes(
    db: Session, user: User, title_id: int
) -> set[tuple[int, int]]:
    rows = db.scalars(
        select(WatchEvent).where(
            WatchEvent.user_id == user.id, WatchEvent.title_id == title_id
        )
    ).all()
    return {(r.season, r.episode) for r in rows}


def get_stats(db: Session, user: User) -> dict:
    """Totals for the profile page: counts and estimated minutes watched."""
    events = db.scalars(
        select(WatchEvent).where(WatchEvent.user_id == user.id)
    ).all()
    if not events:
        return {"episodes": 0, "movies": 0, "minutes": 0}

    title_ids = {e.title_id for e in events}
    titles = db.scalars(select(Title).where(Title.id.in_(title_ids))).all()
    runtime_by_title: dict[int, int | None] = {}
    for t in titles:
        runtime = None
        if t.cached_metadata:
            try:
                runtime = json.loads(t.cached_metadata).get("runtime")
            except json.JSONDecodeError:
                runtime = None
        runtime_by_title[t.id] = runtime

    episodes = movies = minutes = 0
    for e in events:
        runtime = runtime_by_title.get(e.title_id)
        if e.season == 0 and e.episode == 0:
            movies += 1
            minutes += runtime or 110
        else:
            episodes += 1
            minutes += runtime or 45
    return {"episodes": episodes, "movies": movies, "minutes": minutes}


def _ensure_watch_event(
    db: Session, user_id: int, title_id: int, season: int, episode: int
) -> None:
    existing = db.scalar(
        select(WatchEvent).where(
            WatchEvent.user_id == user_id,
            WatchEvent.title_id == title_id,
            WatchEvent.season == season,
            WatchEvent.episode == episode,
        )
    )
    if not existing:
        db.add(
            WatchEvent(
                user_id=user_id, title_id=title_id, season=season, episode=episode
            )
        )


def _remove_watch_event(
    db: Session, user_id: int, title_id: int, season: int, episode: int
) -> None:
    db.execute(
        delete(WatchEvent).where(
            WatchEvent.user_id == user_id,
            WatchEvent.title_id == title_id,
            WatchEvent.season == season,
            WatchEvent.episode == episode,
        )
    )


def _season_map(title: Title) -> dict[int, int]:
    """season_number -> episode_count from cached metadata."""
    if not title.cached_metadata:
        return {}
    try:
        seasons = json.loads(title.cached_metadata).get("seasons") or []
    except json.JSONDecodeError:
        return {}
    out: dict[int, int] = {}
    for s in seasons:
        sn = s.get("season_number")
        if sn is None:
            continue
        out[int(sn)] = int(s.get("episode_count") or 0)
    return out


def previous_episodes(
    title: Title, season: int, episode: int
) -> list[tuple[int, int]]:
    """All episodes before (season, episode), in order."""
    counts = _season_map(title)
    if not counts:
        return [(season, e) for e in range(1, episode)]
    prev: list[tuple[int, int]] = []
    for sn in sorted(counts):
        if sn > season:
            break
        last = episode - 1 if sn == season else counts[sn]
        for e in range(1, last + 1):
            prev.append((sn, e))
    return prev


def first_unwatched_episode(
    title: Title, watched: set[tuple[int, int]]
) -> tuple[int, int] | None:
    """First unwatched episode in numbered seasons (skips season 0 specials).

    Returns None when every numbered episode is watched. Returns None
    without distinguishing "no season metadata" — callers must check
    ``_season_map`` when they need that split.
    """
    counts = _season_map(title)
    for sn in sorted(counts):
        if sn < 1:
            continue
        for episode in range(1, counts[sn] + 1):
            if (sn, episode) not in watched:
                return sn, episode
    return None


def compute_watch_cursor(
    title: Title, watched: set[tuple[int, int]]
) -> tuple[WatchStatus, int | None, int | None] | None:
    """Watch-next cursor from watch events + cached episode counts.

    None means cached metadata has no numbered seasons, so the cursor
    cannot be computed this way.
    """
    counts = _season_map(title)
    if not any(sn >= 1 and n > 0 for sn, n in counts.items()):
        return None
    nxt = first_unwatched_episode(title, watched)
    if nxt:
        return WatchStatus.watching, nxt[0], nxt[1]
    return WatchStatus.watched, None, None


def sync_watch_cursor(db: Session, user: User, row: UserTitle) -> bool:
    """Set current_season/episode to the first unwatched numbered episode.

    Does not commit. Returns True when status or cursor changed.
    """
    if row.title.media_type != MediaType.tv:
        return False
    db.flush()
    watched = list_watched_episodes(db, user, row.title_id)
    computed = compute_watch_cursor(row.title, watched)
    if computed is None:
        return False
    status, season, episode = computed
    if (
        row.status == status
        and row.current_season == season
        and row.current_episode == episode
    ):
        return False
    row.status = status
    row.current_season = season
    row.current_episode = episode
    return True


def _apply_computed_cursor(
    row: UserTitle,
    watched: set[tuple[int, int]],
    tmdb: TmdbClient,
    fallback_season: int,
    fallback_episode: int,
) -> tuple[int, int] | None:
    """Apply watch-next from events, or next_episode if season counts are missing.

    Returns the next (season, episode), or None when the show is finished.
    """
    computed = compute_watch_cursor(row.title, watched)
    if computed is not None:
        status, season, episode = computed
        row.status = status
        row.current_season = season
        row.current_episode = episode
        if season is None or episode is None:
            return None
        return season, episode

    seasons = None
    if row.title.cached_metadata:
        try:
            seasons = json.loads(row.title.cached_metadata).get("seasons")
        except json.JSONDecodeError:
            seasons = None
    nxt = tmdb.next_episode(
        row.title.tmdb_id, fallback_season, fallback_episode, seasons
    )
    row.status = WatchStatus.watching
    if nxt:
        row.current_season = nxt.season
        row.current_episode = nxt.episode
        return nxt.season, nxt.episode
    row.status = WatchStatus.watched
    row.current_season = None
    row.current_episode = None
    return None


def mark_specific_episode(
    db: Session,
    tmdb: TmdbClient,
    user: User,
    user_title_id: int,
    season: int,
    episode: int,
    mark_previous: bool = False,
) -> tuple[UserTitle | None, str, int]:
    """
    Mark one episode watched. If mark_previous, also mark every earlier episode.
    Returns (row, message, previous_marked_count).
    """
    row = get_library_row(db, user, user_title_id)
    if not row:
        return None, "Title not found in your list.", 0
    if row.title.media_type != MediaType.tv:
        return None, "Only TV shows have episodes.", 0

    previous_count = 0
    if mark_previous:
        watched = list_watched_episodes(db, user, row.title_id)
        for s, e in previous_episodes(row.title, season, episode):
            if (s, e) not in watched:
                _ensure_watch_event(db, user.id, row.title_id, s, e)
                previous_count += 1

    _ensure_watch_event(db, user.id, row.title_id, season, episode)

    db.flush()
    watched = list_watched_episodes(db, user, row.title_id)
    nxt = _apply_computed_cursor(row, watched, tmdb, season, episode)
    if nxt:
        msg = f"Marked S{season}E{episode}. Next up: S{nxt[0]}E{nxt[1]}"
    else:
        msg = f"Marked S{season}E{episode}. Show finished."

    db.commit()
    db.refresh(row)
    return row, msg, previous_count


def unmark_specific_episode(
    db: Session, user: User, user_title_id: int, season: int, episode: int
) -> UserTitle | None:
    row = get_library_row(db, user, user_title_id)
    if not row or row.title.media_type != MediaType.tv:
        return None
    _remove_watch_event(db, user.id, row.title_id, season, episode)
    if not sync_watch_cursor(db, user, row):
        row.status = WatchStatus.watching
        row.current_season = season
        row.current_episode = episode
    db.commit()
    db.refresh(row)
    return row


def mark_season(
    db: Session,
    tmdb: TmdbClient,
    user: User,
    user_title_id: int,
    season: int,
    mark_previous: bool = True,
) -> tuple[UserTitle | None, str]:
    """Mark every episode in a season as watched.

    If mark_previous, also mark earlier seasons — same set as
    previous_episodes() / episode mark_previous (includes specials
    only when they are already in cached season metadata).
    """
    row = get_library_row(db, user, user_title_id)
    if not row:
        return None, "Title not found in your list."
    if row.title.media_type != MediaType.tv:
        return None, "Only TV shows have seasons."

    counts = _season_map(row.title)
    total = counts.get(season)
    if not total:
        return None, f"No episodes found for season {season}."

    if mark_previous:
        for s, e in previous_episodes(row.title, season, 1):
            _ensure_watch_event(db, user.id, row.title_id, s, e)

    for e in range(1, total + 1):
        _ensure_watch_event(db, user.id, row.title_id, season, e)

    db.flush()
    watched = list_watched_episodes(db, user, row.title_id)
    nxt = _apply_computed_cursor(row, watched, tmdb, season, total)
    earlier = " including earlier seasons" if mark_previous and season > 1 else ""
    if nxt:
        msg = f"Marked season {season} complete{earlier}."
    else:
        msg = f"Marked season {season} complete{earlier}. Show finished."

    db.commit()
    db.refresh(row)
    return row, msg


def unmark_season(
    db: Session, user: User, user_title_id: int, season: int
) -> UserTitle | None:
    row = get_library_row(db, user, user_title_id)
    if not row or row.title.media_type != MediaType.tv:
        return None
    counts = _season_map(row.title)
    total = counts.get(season, 0)
    for e in range(1, total + 1):
        _remove_watch_event(db, user.id, row.title_id, season, e)
    if not sync_watch_cursor(db, user, row):
        row.status = WatchStatus.watching
        row.current_season = season
        row.current_episode = 1
    db.commit()
    db.refresh(row)
    return row


def mark_all_episodes(
    db: Session, user: User, user_title_id: int
) -> tuple[UserTitle | None, str]:
    row = get_library_row(db, user, user_title_id)
    if not row:
        return None, "Title not found in your list."
    if row.title.media_type != MediaType.tv:
        return None, "Only TV shows have episodes."
    counts = _season_map(row.title)
    for season, total in counts.items():
        for e in range(1, total + 1):
            _ensure_watch_event(db, user.id, row.title_id, season, e)
    if not sync_watch_cursor(db, user, row):
        row.status = WatchStatus.watched
        row.current_season = None
        row.current_episode = None
    db.commit()
    db.refresh(row)
    return row, f"Marked all episodes of {row.title.title}."


def set_user_timezone(db: Session, user: User, timezone_name: str) -> User:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc
    user.timezone = timezone_name
    db.commit()
    db.refresh(user)
    return user


def mark_episode_watched(
    db: Session, tmdb: TmdbClient, user: User, user_title_id: int
) -> tuple[UserTitle | None, str]:
    """Mark current episode done and advance. Returns (row, message)."""
    row = get_library_row(db, user, user_title_id)
    if not row:
        return None, "Title not found in your list."
    if row.title.media_type == MediaType.movie:
        _ensure_watch_event(db, user.id, row.title_id, 0, 0)
        row.status = WatchStatus.watched
        db.commit()
        db.refresh(row)
        return row, f"Marked {row.title.title} as watched."

    season = row.current_season or 1
    episode = row.current_episode or 1
    updated, message, _ = mark_specific_episode(
        db, tmdb, user, user_title_id, season, episode, mark_previous=False
    )
    return updated, message