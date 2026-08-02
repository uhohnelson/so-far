"""Tests for episode air alert logic."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.alerts import (
    alert_already_sent,
    collect_alert_candidates,
    has_aired,
    is_airing_today,
    is_alerts_muted,
    is_recently_aired,
    record_alert_sent,
    resolve_timezone,
    set_alerts_muted,
    user_today,
)
from server.config import Settings
from server.database import Base
from server.models import MediaType, Title, User, UserTitle, WatchStatus
from server.tmdb import EpisodeInfo


class MapTmdb:
    """TMDB stub keyed by (season, episode) → EpisodeInfo."""

    def __init__(self, episodes: dict[tuple[int, int], EpisodeInfo]):
        self.episodes = episodes

    def get_episode(self, tmdb_id, season, episode):
        return self.episodes.get((season, episode))

    def next_episode(self, tmdb_id, season, episode, seasons=None):
        keys = sorted(self.episodes)
        for s, e in keys:
            if (s, e) > (season, episode):
                return self.episodes[(s, e)]
        return None


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'alerts.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _settings(**kwargs) -> Settings:
    base = dict(
        telegram_bot_token="x",
        tmdb_api_key="y",
        database_url="sqlite:///:memory:",
        default_timezone="America/New_York",
        alert_lookback_days=1,
    )
    base.update(kwargs)
    return Settings(**base)


def _watching_row(db, *, telegram_id=1, tmdb_id=100, title="Show", season=1, episode=1):
    user = User(telegram_id=telegram_id, display_name="U", timezone="America/New_York")
    show = Title(
        tmdb_id=tmdb_id,
        media_type=MediaType.tv,
        title=title,
        year=2020,
        cached_metadata='{"seasons":[{"season_number":1,"episode_count":10}]}',
    )
    db.add_all([user, show])
    db.commit()
    row = UserTitle(
        user_id=user.id,
        title_id=show.id,
        status=WatchStatus.watching,
        current_season=season,
        current_episode=episode,
    )
    db.add(row)
    db.commit()
    return user, show, row


def test_user_today_respects_timezone():
    tz = ZoneInfo("America/Los_Angeles")
    # 2026-07-27 06:00 UTC is still 2026-07-26 in LA
    now = datetime(2026, 7, 27, 6, 0, tzinfo=timezone.utc)
    assert user_today(tz, now).isoformat() == "2026-07-26"
    assert is_airing_today("2026-07-26", tz, now) is True
    assert is_airing_today("2026-07-27", tz, now) is False


def test_has_aired_includes_past_dates():
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)
    assert has_aired("2026-07-27", tz, now) is True
    assert has_aired("2026-07-28", tz, now) is False


def test_is_recently_aired_window():
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)
    assert is_recently_aired("2026-07-27", tz, now, lookback_days=1) is True
    assert is_recently_aired("2026-07-26", tz, now, lookback_days=1) is True
    assert is_recently_aired("2026-07-25", tz, now, lookback_days=1) is False
    assert is_recently_aired("2016-01-01", tz, now, lookback_days=1) is False
    assert is_recently_aired("2026-07-28", tz, now, lookback_days=1) is False


def test_alert_dedup(db_session):
    user = User(telegram_id=1, display_name="U")
    title = Title(
        tmdb_id=99,
        media_type=MediaType.tv,
        title="Test Show",
        year=2020,
    )
    db_session.add_all([user, title])
    db_session.commit()

    assert alert_already_sent(db_session, user.id, title.id, 1, 5) is False
    record_alert_sent(db_session, user.id, title.id, 1, 5)
    assert alert_already_sent(db_session, user.id, title.id, 1, 5) is True
    record_alert_sent(db_session, user.id, title.id, 1, 5)
    assert alert_already_sent(db_session, user.id, title.id, 1, 5) is True


def test_old_unwatched_episode_no_alert(db_session):
    """Back-catalog catch-up must not spam Telegram."""
    _watching_row(db_session, season=1, episode=1)
    tmdb = MapTmdb(
        {
            (1, 1): EpisodeInfo(
                season=1, episode=1, name="Pilot", air_date="2016-01-15"
            ),
        }
    )
    now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)
    candidates = collect_alert_candidates(db_session, tmdb, _settings(), now)
    assert candidates == []


def test_episode_airing_today_alerts_once(db_session):
    user, show, _row = _watching_row(db_session, season=1, episode=5)
    tmdb = MapTmdb(
        {
            (1, 5): EpisodeInfo(
                season=1, episode=5, name="Finale", air_date="2026-07-27"
            ),
        }
    )
    settings = _settings()
    now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)

    candidates = collect_alert_candidates(db_session, tmdb, settings, now)
    assert len(candidates) == 1
    assert candidates[0].episode.episode == 5
    assert candidates[0].airing_today is True

    record_alert_sent(db_session, user.id, show.id, 1, 5)
    candidates = collect_alert_candidates(db_session, tmdb, settings, now)
    assert candidates == []


def test_yesterday_within_lookback_alerts(db_session):
    _watching_row(db_session, season=1, episode=5)
    tmdb = MapTmdb(
        {
            (1, 5): EpisodeInfo(
                season=1, episode=5, name="Finale", air_date="2026-07-26"
            ),
        }
    )
    now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)
    candidates = collect_alert_candidates(db_session, tmdb, _settings(), now)
    assert len(candidates) == 1
    assert candidates[0].airing_today is False


def test_mark_watched_next_old_episode_no_alert(db_session):
    """Advancing into already-available older episodes must not alert."""
    _watching_row(db_session, season=1, episode=2)
    tmdb = MapTmdb(
        {
            (1, 2): EpisodeInfo(
                season=1, episode=2, name="Next", air_date="2016-01-22"
            ),
        }
    )
    now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)
    assert collect_alert_candidates(db_session, tmdb, _settings(), now) == []


def test_future_episode_no_alert(db_session):
    _watching_row(db_session, season=1, episode=5)
    tmdb = MapTmdb(
        {
            (1, 5): EpisodeInfo(
                season=1, episode=5, name="Finale", air_date="2026-08-01"
            ),
        }
    )
    now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)
    assert collect_alert_candidates(db_session, tmdb, _settings(), now) == []


def test_muted_show_skipped(db_session):
    user, show, _row = _watching_row(
        db_session, telegram_id=2, tmdb_id=100, title="Muted Show", season=1, episode=5
    )
    tmdb = MapTmdb(
        {
            (1, 5): EpisodeInfo(
                season=1, episode=5, name="Finale", air_date="2026-07-27"
            ),
        }
    )
    settings = _settings()
    now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)

    candidates = collect_alert_candidates(db_session, tmdb, settings, now)
    assert len(candidates) == 1

    set_alerts_muted(db_session, user, show.id, True)
    assert is_alerts_muted(db_session, user.id, show.id) is True
    candidates = collect_alert_candidates(db_session, tmdb, settings, now)
    assert candidates == []


def test_want_status_not_alerted(db_session):
    user = User(telegram_id=9, display_name="U", timezone="America/New_York")
    show = Title(
        tmdb_id=200,
        media_type=MediaType.tv,
        title="Want Show",
        year=2020,
    )
    db_session.add_all([user, show])
    db_session.commit()
    db_session.add(
        UserTitle(
            user_id=user.id,
            title_id=show.id,
            status=WatchStatus.want,
            current_season=1,
            current_episode=1,
        )
    )
    db_session.commit()
    tmdb = MapTmdb(
        {
            (1, 1): EpisodeInfo(
                season=1, episode=1, name="Pilot", air_date="2026-07-27"
            ),
        }
    )
    now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)
    assert collect_alert_candidates(db_session, tmdb, _settings(), now) == []


def test_resolve_timezone_falls_back_to_default(db_session):
    user = User(telegram_id=3, display_name="U", timezone=None)
    db_session.add(user)
    db_session.commit()
    settings = _settings(default_timezone="America/Chicago")
    assert str(resolve_timezone(user, settings)) == "America/Chicago"
