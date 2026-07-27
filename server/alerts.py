"""Episode air-date alert logic (Phase 2). Pure helpers + scheduler runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from server.config import Settings, get_settings
from server.models import AlertPref, AlertSent, MediaType, User, UserTitle, WatchStatus
from server.tmdb import EpisodeInfo, TmdbClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertCandidate:
    user: User
    row: UserTitle
    episode: EpisodeInfo
    airing_today: bool


def resolve_timezone(user: User | None, settings: Settings | None = None) -> ZoneInfo:
    settings = settings or get_settings()
    raw = (user.timezone if user else None) or settings.default_timezone
    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        return ZoneInfo(settings.default_timezone)


def user_today(tz: ZoneInfo, now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(tz).date()


def parse_air_date(air_date: str | None) -> date | None:
    if not air_date or len(air_date) < 10:
        return None
    try:
        return date.fromisoformat(air_date[:10])
    except ValueError:
        return None


def is_airing_today(
    air_date: str | None,
    tz: ZoneInfo,
    now: datetime | None = None,
) -> bool:
    ad = parse_air_date(air_date)
    if ad is None:
        return False
    return ad == user_today(tz, now)


def has_aired(
    air_date: str | None,
    tz: ZoneInfo,
    now: datetime | None = None,
) -> bool:
    ad = parse_air_date(air_date)
    if ad is None:
        return False
    return ad <= user_today(tz, now)


def timezone_abbr(tz: ZoneInfo, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    label = now.astimezone(tz).tzname() or ""
    return label or str(tz)


def is_alerts_muted(db: Session, user_id: int, title_id: int) -> bool:
    pref = db.scalar(
        select(AlertPref).where(
            AlertPref.user_id == user_id,
            AlertPref.title_id == title_id,
        )
    )
    return bool(pref and pref.muted)


def set_alerts_muted(
    db: Session, user: User, title_id: int, muted: bool
) -> AlertPref:
    pref = db.scalar(
        select(AlertPref).where(
            AlertPref.user_id == user.id,
            AlertPref.title_id == title_id,
        )
    )
    if pref:
        pref.muted = muted
    else:
        pref = AlertPref(user_id=user.id, title_id=title_id, muted=muted)
        db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref


def alert_already_sent(
    db: Session, user_id: int, title_id: int, season: int, episode: int
) -> bool:
    row = db.scalar(
        select(AlertSent).where(
            AlertSent.user_id == user_id,
            AlertSent.title_id == title_id,
            AlertSent.season == season,
            AlertSent.episode == episode,
        )
    )
    return row is not None


def record_alert_sent(
    db: Session, user_id: int, title_id: int, season: int, episode: int
) -> None:
    if alert_already_sent(db, user_id, title_id, season, episode):
        return
    db.add(
        AlertSent(
            user_id=user_id,
            title_id=title_id,
            season=season,
            episode=episode,
        )
    )
    db.commit()


def find_due_episode(
    tmdb: TmdbClient,
    row: UserTitle,
    tz: ZoneInfo,
    now: datetime | None = None,
) -> tuple[EpisodeInfo | None, bool]:
    """First episode at/after cursor with air_date on or before today in ``tz``."""
    if row.title.media_type != MediaType.tv:
        return None, False

    season = row.current_season or 1
    episode = row.current_episode or 1
    seasons_meta = None
    if row.title.cached_metadata:
        import json

        try:
            seasons_meta = json.loads(row.title.cached_metadata).get("seasons")
        except json.JSONDecodeError:
            seasons_meta = None

    cursor_season, cursor_episode = season, episode
    # Walk forward from cursor; alert the first episode that has aired (incl. today).
    for _ in range(64):
        ep = tmdb.get_episode(row.title.tmdb_id, cursor_season, cursor_episode)
        if ep is None:
            nxt = tmdb.next_episode(
                row.title.tmdb_id,
                cursor_season,
                cursor_episode,
                seasons_meta,
            )
            if nxt is None:
                break
            cursor_season, cursor_episode = nxt.season, nxt.episode
            ep = nxt

        if ep.air_date and has_aired(ep.air_date, tz, now):
            return ep, is_airing_today(ep.air_date, tz, now)

        nxt = tmdb.next_episode(
            row.title.tmdb_id, cursor_season, cursor_episode, seasons_meta
        )
        if nxt is None:
            break
        cursor_season, cursor_episode = nxt.season, nxt.episode

    return None, False


def collect_alert_candidates(
    db: Session,
    tmdb: TmdbClient,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> list[AlertCandidate]:
    settings = settings or get_settings()
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(
        select(UserTitle)
        .options(joinedload(UserTitle.title), joinedload(UserTitle.user))
        .where(
            UserTitle.status == WatchStatus.watching,
        )
    ).unique().all()

    out: list[AlertCandidate] = []
    for row in rows:
        if row.title.media_type != MediaType.tv:
            continue
        if is_alerts_muted(db, row.user_id, row.title_id):
            continue
        tz = resolve_timezone(row.user, settings)
        ep, airing_today = find_due_episode(tmdb, row, tz, now)
        if ep is None:
            continue
        if alert_already_sent(db, row.user_id, row.title_id, ep.season, ep.episode):
            continue
        out.append(
            AlertCandidate(
                user=row.user,
                row=row,
                episode=ep,
                airing_today=airing_today,
            )
        )
    return out


def format_alert_message(
    candidate: AlertCandidate,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> str:
    settings = settings or get_settings()
    show = candidate.row.title.title
    ep = candidate.episode
    title_bit = f" '{ep.name}'" if ep.name else ""
    tz = resolve_timezone(candidate.user, settings)
    if candidate.airing_today:
        when = f"airs today ({timezone_abbr(tz, now)})"
    else:
        when = "aired recently"
    return (
        f"🎬 New episode — {show} S{ep.season}E{ep.episode}{title_bit} {when}."
    )
