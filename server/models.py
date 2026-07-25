from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.database import Base


class MediaType(str, enum.Enum):
    movie = "movie"
    tv = "tv"


class WatchStatus(str, enum.Enum):
    want = "want"
    watching = "watching"
    watched = "watched"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    library: Mapped[list[UserTitle]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Title(Base):
    __tablename__ = "titles"
    __table_args__ = (UniqueConstraint("tmdb_id", "media_type", name="uq_title_tmdb_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    cached_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    library_rows: Mapped[list[UserTitle]] = relationship(back_populates="title")


class UserTitle(Base):
    __tablename__ = "user_titles"
    __table_args__ = (UniqueConstraint("user_id", "title_id", name="uq_user_title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[WatchStatus] = mapped_column(Enum(WatchStatus), nullable=False, index=True)
    current_season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="library")
    title: Mapped[Title] = relationship(back_populates="library_rows")
