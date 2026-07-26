from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from server.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    db_path = url.removeprefix("sqlite:///")
    if db_path in {":memory:", ""}:
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


settings = get_settings()
_ensure_sqlite_dir(settings.database_url)

_is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if _is_sqlite else {}

# SQLite cannot take a QueuePool under concurrent FastAPI requests: each
# season/TMDB call was holding a connection and exhausting the pool (30s waits).
if _is_sqlite:
    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        poolclass=StaticPool,
    )
else:
    engine = create_engine(settings.database_url, connect_args=connect_args)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from sqlalchemy import inspect, text

    from server import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Lightweight SQLite column adds for existing installs.
    if settings.database_url.startswith("sqlite"):
        insp = inspect(engine)
        if "users" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("users")}
            if "cover_title_id" not in cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN cover_title_id INTEGER "
                            "REFERENCES titles(id) ON DELETE SET NULL"
                        )
                    )
        if "api_tokens" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("api_tokens")}
            if "expires_at" not in cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE api_tokens ADD COLUMN expires_at DATETIME"
                        )
                    )
                    # Token hashing landed with expires_at: plaintext rows are
                    # unverifiable. Users must /app re-login.
                    conn.execute(text("DELETE FROM api_tokens"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
