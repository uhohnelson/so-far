"""End-to-end checks for the web app API: login codes, auth guard, library CRUD."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server import api as api_module
from server import services
from server.database import Base, get_db
from server.tmdb import (
    CastMember,
    EpisodeInfo,
    SearchResult,
    SeasonSummary,
    TitleDetail,
)


class FakeTmdb:
    def search(self, query, limit=8, media_type=None):
        return [
            SearchResult(
                tmdb_id=1396,
                media_type="tv",
                title="Breaking Bad",
                year=2008,
                overview="A teacher turns to crime.",
                poster_path="/bb.jpg",
                backdrop_path="/bb-bd.jpg",
            )
        ]

    def trending(self, limit=8, media_type=None):
        return self.search("x", limit=limit)

    def top_rated(self, media_type, limit=8):
        return self.search("x", limit=limit, media_type=media_type)

    def get_title(self, media_type, tmdb_id):
        return TitleDetail(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title="Breaking Bad",
            year=2008,
            overview="A teacher turns to crime.",
            poster_path="/bb.jpg",
            backdrop_path="/bb-bd.jpg",
            tagline="All hail the king",
            genres=["Drama", "Crime"],
            runtime=47,
            status="Ended",
            vote_average=9.0,
            networks=["AMC"],
            number_of_seasons=1,
            number_of_episodes=7,
            seasons=[
                SeasonSummary(
                    season_number=1, episode_count=7, name="Season 1"
                )
            ],
            cast=[
                CastMember(
                    id=1, name="Bryan Cranston", character="Walter White", profile_path="/bc.jpg"
                )
            ],
            release_date="2008-01-20",
            trailer_key="XZ8daibM3AE",
            providers=[{"name": "Netflix", "logo_path": "/nf.jpg"}],
        )

    def get_season_episodes(self, tmdb_id, season):
        return [
            EpisodeInfo(
                season=season,
                episode=i,
                name=f"Ep {i}",
                air_date="2008-01-01",
                overview="...",
                still_path=f"/e{i}.jpg",
                runtime=47,
            )
            for i in range(1, 8)
        ]

    def next_episode(self, tmdb_id, season, episode, seasons=None):
        if episode < 7:
            return EpisodeInfo(season=season, episode=episode + 1, name="Next", air_date=None)
        return None

    def poster_url(self, poster_path, size="w500"):
        return f"https://image.tmdb.org/t/p/{size}{poster_path}" if poster_path else None


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(api_module, "TmdbClient", lambda *a, **k: FakeTmdb())
    monkeypatch.setattr(api_module, "init_db", lambda: None)

    app = api_module.create_app()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        c.session_factory = TestingSession  # type: ignore[attr-defined]
        yield c


def _login(client) -> str:
    db = client.session_factory()
    try:
        user = services.get_or_create_user(db, 5551234, "Tester")
        code = services.create_login_code(db, user).code
    finally:
        db.close()
    res = client.post("/api/auth/exchange", json={"code": code})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_library_requires_auth(client):
    assert client.get("/api/library").status_code == 401


def test_discover_feeds_support_movies_and_tv(client):
    token = _login(client)
    for media_type in ("movie", "tv"):
        trending = client.get(
            "/api/trending",
            headers=_auth(token),
            params={"media_type": media_type},
        )
        top = client.get(
            "/api/top-rated",
            headers=_auth(token),
            params={"media_type": media_type},
        )
        assert trending.status_code == 200
        assert top.status_code == 200


def test_title_detail_includes_cast_and_genres(client):
    token = _login(client)
    res = client.get("/api/titles/tv/1396", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert body["title"]["genres"] == ["Drama", "Crime"]
    assert body["title"]["cast"][0]["name"] == "Bryan Cranston"
    assert body["library_item"] is None


def test_title_detail_providers_trailer_and_date(client):
    token = _login(client)
    body = client.get("/api/titles/tv/1396", headers=_auth(token)).json()
    assert body["title"]["release_date"] == "2008-01-20"
    assert body["title"]["trailer_url"] == "https://www.youtube.com/watch?v=XZ8daibM3AE"
    assert body["title"]["providers"] == [
        {"name": "Netflix", "logo_url": "https://image.tmdb.org/t/p/w92/nf.jpg"}
    ]


def test_stats_counts_episodes_and_minutes(client):
    token = _login(client)
    empty = client.get("/api/stats", headers=_auth(token)).json()
    assert empty == {"episodes": 0, "movies": 0, "minutes": 0}

    add = client.post(
        "/api/library",
        headers=_auth(token),
        json={"tmdb_id": 1396, "media_type": "tv", "status": "watching"},
    )
    item_id = add.json()["id"]
    client.post(
        f"/api/library/{item_id}/episodes",
        headers=_auth(token),
        json={"season": 1, "episode": 5, "mark_previous": True},
    )

    stats = client.get("/api/stats", headers=_auth(token)).json()
    assert stats["episodes"] == 5
    assert stats["movies"] == 0
    assert stats["minutes"] == 5 * 47


def test_mark_season_and_all(client):
    token = _login(client)
    item_id = client.post(
        "/api/library",
        headers=_auth(token),
        json={"tmdb_id": 1396, "media_type": "tv", "status": "watching"},
    ).json()["id"]

    marked = client.post(
        f"/api/library/{item_id}/seasons/1", headers=_auth(token)
    )
    assert marked.status_code == 200
    detail = client.get("/api/titles/tv/1396", headers=_auth(token)).json()
    assert len(detail["watched_episodes"]) == 7
    assert all(k.startswith("S1E") for k in detail["watched_episodes"])

    client.delete(f"/api/library/{item_id}/seasons/1", headers=_auth(token))
    detail = client.get("/api/titles/tv/1396", headers=_auth(token)).json()
    assert detail["watched_episodes"] == []

    client.post(f"/api/library/{item_id}/seasons/all", headers=_auth(token))
    detail = client.get("/api/titles/tv/1396", headers=_auth(token)).json()
    assert len(detail["watched_episodes"]) == 7
    assert detail["library_item"]["status"] == "watched"


def test_season_episodes_and_mark_previous(client):
    token = _login(client)
    add = client.post(
        "/api/library",
        headers=_auth(token),
        json={"tmdb_id": 1396, "media_type": "tv", "status": "watching"},
    )
    item_id = add.json()["id"]

    eps = client.get("/api/titles/tv/1396/season/1", headers=_auth(token))
    assert eps.status_code == 200
    assert len(eps.json()["episodes"]) == 7
    assert eps.json()["episodes"][0]["watched"] is False

    preview = client.get(
        f"/api/library/{item_id}/episodes/preview",
        headers=_auth(token),
        params={"season": 1, "episode": 5},
    )
    assert preview.json()["previous_unwatched"] == 4

    marked = client.post(
        f"/api/library/{item_id}/episodes",
        headers=_auth(token),
        json={"season": 1, "episode": 5, "mark_previous": True},
    )
    assert marked.status_code == 200
    assert marked.json()["previous_marked"] == 4
    assert marked.json()["item"]["current_episode"] == 6

    eps2 = client.get("/api/titles/tv/1396/season/1", headers=_auth(token))
    watched_flags = [e["watched"] for e in eps2.json()["episodes"]]
    assert watched_flags[:5] == [True, True, True, True, True]
    assert watched_flags[5] is False


def test_code_is_single_use(client):
    db = client.session_factory()
    try:
        user = services.get_or_create_user(db, 777, None)
        code = services.create_login_code(db, user).code
    finally:
        db.close()
    assert client.post("/api/auth/exchange", json={"code": code}).status_code == 200
    assert client.post("/api/auth/exchange", json={"code": code}).status_code == 401


def test_add_progress_and_remove_flow(client):
    token = _login(client)
    res = client.post(
        "/api/library",
        headers=_auth(token),
        json={"tmdb_id": 1396, "media_type": "tv", "status": "watching"},
    )
    item = res.json()
    assert item["current_season"] == 1
    item_id = item["id"]

    res = client.post(
        f"/api/library/{item_id}/progress", headers=_auth(token), json={"season": 1, "episode": 4}
    )
    assert res.json()["current_episode"] == 4

    res = client.post(f"/api/library/{item_id}/watched", headers=_auth(token))
    assert res.json()["item"]["current_episode"] == 5

    assert client.delete(f"/api/library/{item_id}", headers=_auth(token)).status_code == 200
