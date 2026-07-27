"""Send episode alerts via Telegram (invoked from bot job queue)."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from server.alerts import (
    collect_alert_candidates,
    format_alert_message,
    record_alert_sent,
)
from server.config import get_settings
from server.database import SessionLocal
from server.models import UserTitle
from server.tmdb import TmdbClient

logger = logging.getLogger(__name__)


def _short_name(name: str, limit: int = 28) -> str:
    name = name.strip()
    if len(name) <= limit:
        return name
    return name[: limit - 1] + "…"


def _alert_keyboard(row: UserTitle) -> InlineKeyboardMarkup:
    settings = get_settings()
    name = _short_name(row.title.title)
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(f"Mark watched · {name}", callback_data=f"watched:{row.id}")]
    ]
    if settings.web_app_url:
        base = settings.web_app_url.rstrip("/")
        rows.append([InlineKeyboardButton("Open in Sofar", url=base)])
    rows.append([InlineKeyboardButton(f"Mute · {name}", callback_data=f"mute:{row.id}")])
    return InlineKeyboardMarkup(rows)


async def run_episode_alerts(bot, tmdb: TmdbClient) -> int:
    """Check watching shows and DM users. Returns count sent."""
    settings = get_settings()
    db = SessionLocal()
    sent = 0
    try:
        candidates = collect_alert_candidates(db, tmdb, settings)
        for cand in candidates:
            text = format_alert_message(cand, settings)
            try:
                await bot.send_message(
                    chat_id=cand.user.telegram_id,
                    text=text,
                    reply_markup=_alert_keyboard(cand.row),
                    parse_mode=ParseMode.HTML,
                )
                record_alert_sent(
                    db,
                    cand.user.id,
                    cand.row.title_id,
                    cand.episode.season,
                    cand.episode.episode,
                )
                sent += 1
            except Exception:
                logger.exception(
                    "Failed to send alert to telegram_id=%s show=%s S%sE%s",
                    cand.user.telegram_id,
                    cand.row.title.title,
                    cand.episode.season,
                    cand.episode.episode,
                )
    finally:
        db.close()
    if sent:
        logger.info("Episode alerts sent: %d", sent)
    return sent
