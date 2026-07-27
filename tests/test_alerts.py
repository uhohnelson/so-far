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
    record_alert_sent,
    resolve_timezone,
    set_alerts_muted,
    user_today,
)
from server.config import Settings
from server.database import Base
from server.models import MediaType, Title, User, UserTitle, WatchStatus
from server.tmdb import EpisodeInfo


class AlertTmdb:
    def get_episode(self, tmdb_id, season, episode):
        if season == 1 and episode == 5:
            return EpisodeInfo(
                season=1,
                episode=5,
                name="Finale",
                air_date="2026-07-27",
            )
        return None

    def next_episode(self, tmdb_id, season, episode, seasons=None):
        if season == 1 and episode == 4:
            return EpisodeInfo(
                season=1,
                episode=5,
                name="Finale",
                air_date="2026-07-27",
            )
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


def test_muted_show_skipped(db_session):
    user = User(telegram_id=2, display_name="U", timezone="America/New_York")
    title = Title(
        tmdb_id=100,
        media_type=MediaType.tv,
        title="Muted Show",
        year=2020,
        cached_metadata='{"seasons":[{"season_number":1,"episode_count":5}]}',
    )
    db_session.add_all([user, title])
    db_session.commit()
    row = UserTitle(
        user_id=user.id,
        title_id=title.id,
        status=WatchStatus.watching,
        current_season=1,
        current_episode=5,
    )
    db_session.add(row)
    db_session.commit()

    settings = Settings(
        telegram_bot_token="x",
        tmdb_api_key="y",
        database_url="sqlite:///:memory:",
        default_timezone="America/New_York",
    )
    now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)
    tmdb = AlertTmdb()
    candidates = collect_alert_candidates(db_session, tmdb, settings, now)
    assert len(candidates) == 1

    set_alerts_muted(db_session, user, title.id, True)
    assert is_alerts_muted(db_session, user.id, title.id) is True
    candidates = collect_alert_candidates(db_session, tmdb, settings, now)
    assert candidates == []


def test_resolve_timezone_falls_back_to_default(db_session):
    user = User(telegram_id=3, display_name="U", timezone=None)
    db_session.add(user)
    db_session.commit()
    settings = Settings(
        telegram_bot_token="x",
        tmdb_api_key="y",
        database_url="sqlite:///:memory:",
        default_timezone="America/Chicago",
    )
    assert str(resolve_timezone(user, settings)) == "America/Chicago"
