"""TMDB season cache should not treat empty/404 as a long-lived success."""

from __future__ import annotations

import time

import httpx
import pytest

from server.config import Settings
from server.tmdb import (
    TmdbClient,
    _SEASON_CACHE_TTL_SEC,
    _SEASON_EMPTY_CACHE_TTL_SEC,
)


@pytest.fixture
def tmdb():
    client = TmdbClient(Settings(telegram_bot_token="t", tmdb_api_key="k"))
    try:
        yield client
    finally:
        client.close()


def test_empty_season_uses_short_ttl(tmdb, monkeypatch):
    calls = {"n": 0}

    def fake_get(path, params=None):
        calls["n"] += 1
        return {"episodes": []}

    monkeypatch.setattr(tmdb, "_get", fake_get)
    assert tmdb.get_season_episodes(97546, 4) == []
    assert tmdb.get_season_episodes(97546, 4) == []
    assert calls["n"] == 1
    entry = tmdb._season_cache[(97546, 4)]
    remaining = entry.expires_at - time.monotonic()
    assert remaining <= _SEASON_EMPTY_CACHE_TTL_SEC + 1
    assert remaining < _SEASON_CACHE_TTL_SEC / 2


def test_season_404_uses_short_ttl(tmdb, monkeypatch):
    calls = {"n": 0}

    def fake_get(path, params=None):
        calls["n"] += 1
        request = httpx.Request("GET", "https://example.com/tv/1/season/4")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(tmdb, "_get", fake_get)
    assert tmdb.get_season_episodes(97546, 4) == []
    assert tmdb.get_season_episodes(97546, 4) == []
    assert calls["n"] == 1
    remaining = tmdb._season_cache[(97546, 4)].expires_at - time.monotonic()
    assert remaining <= _SEASON_EMPTY_CACHE_TTL_SEC + 1


def test_populated_season_uses_long_ttl(tmdb, monkeypatch):
    def fake_get(path, params=None):
        return {
            "episodes": [
                {
                    "episode_number": 1,
                    "name": "Pilot",
                    "air_date": "2020-08-14",
                    "overview": "",
                    "still_path": None,
                    "runtime": 30,
                }
            ]
        }

    monkeypatch.setattr(tmdb, "_get", fake_get)
    eps = tmdb.get_season_episodes(97546, 1)
    assert len(eps) == 1
    remaining = tmdb._season_cache[(97546, 1)].expires_at - time.monotonic()
    assert remaining > _SEASON_EMPTY_CACHE_TTL_SEC * 2
