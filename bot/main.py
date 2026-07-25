from __future__ import annotations

import html
import logging
import re

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from server import services
from server.config import get_settings
from server.database import SessionLocal, init_db
from server.models import MediaType, UserTitle, WatchStatus
from server.tmdb import SearchResult, TmdbClient

logger = logging.getLogger(__name__)

# One status language everywhere (PRD: zero confusion).
STATUS_LABELS = {
    WatchStatus.want: "Want",
    WatchStatus.watching: "Watching",
    WatchStatus.watched: "Watched",
}

BOT_COMMANDS = [
    BotCommand("start", "Open Sofar"),
    BotCommand("search", "Find a movie or show"),
    BotCommand("list", "Your library"),
    BotCommand("next", "What's next"),
    BotCommand("watched", "Mark episode done"),
    BotCommand("cancel", "Cancel current step"),
    BotCommand("help", "Quick tips"),
]


def _user_meta(update: Update) -> tuple[int, str | None]:
    user = update.effective_user
    assert user is not None
    return user.id, user.full_name or user.username


def _kind_label(media_type) -> str:
    if media_type in (MediaType.movie, "movie"):
        return "Movie"
    return "Show"


def _title_plain(title: str, year: int | None = None, media_type=None) -> str:
    year_bit = f" ({year})" if year else ""
    kind = f" · {_kind_label(media_type)}" if media_type else ""
    return f"{title}{year_bit}{kind}"


def _title_html(title: str, year: int | None = None, media_type=None) -> str:
    year_bit = f" ({year})" if year else ""
    kind = f" · {_kind_label(media_type)}" if media_type else ""
    return f"<b>{html.escape(title)}</b>{html.escape(year_bit + kind)}"


def _progress_bit(row: UserTitle) -> str:
    if row.title.media_type == MediaType.tv and row.current_season and row.current_episode:
        return f" · S{row.current_season}E{row.current_episode}"
    return ""


def _short_name(name: str, limit: int = 28) -> str:
    name = name.strip()
    if len(name) <= limit:
        return name
    return name[: limit - 1] + "…"


def _btn(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label[:64], callback_data=data)


def _search_button(placeholder: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        "Search",
        switch_inline_query_current_chat=placeholder,
    )


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    """TV remote: Search, Continue, My list."""
    return InlineKeyboardMarkup(
        [
            [_search_button()],
            [InlineKeyboardButton("Continue", callback_data="menu:continue")],
            [InlineKeyboardButton("My list", callback_data="menu:list")],
        ]
    )


def _status_keyboard(media_type: str, tmdb_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("Want", f"status:want:{media_type}:{tmdb_id}"),
                _btn("Watching", f"status:watching:{media_type}:{tmdb_id}"),
                _btn("Watched", f"status:watched:{media_type}:{tmdb_id}"),
            ],
            [_search_button(), InlineKeyboardButton("Home", callback_data="menu:home")],
        ]
    )


def _list_filter_keyboard(active: WatchStatus | None = None) -> list[list[InlineKeyboardButton]]:
    def label(status: WatchStatus | None, text: str) -> str:
        if active == status:
            return f"[{text}]"
        return text

    return [
        [
            InlineKeyboardButton(label(None, "All"), callback_data="list:all"),
            InlineKeyboardButton(label(WatchStatus.want, "Want"), callback_data="list:want"),
            InlineKeyboardButton(
                label(WatchStatus.watching, "Watching"), callback_data="list:watching"
            ),
            InlineKeyboardButton(
                label(WatchStatus.watched, "Watched"), callback_data="list:watched"
            ),
        ]
    ]


def _item_actions(row: UserTitle) -> list[list[InlineKeyboardButton]]:
    """One labeled row per title so buttons map to the right show."""
    name = _short_name(row.title.title)
    rows: list[list[InlineKeyboardButton]] = []
    if row.status == WatchStatus.watching:
        if row.title.media_type == MediaType.tv:
            rows.append(
                [
                    _btn(f"Next · {name}", f"next:{row.id}"),
                    _btn(f"Mark ep · {name}", f"watched:{row.id}"),
                ]
            )
        else:
            rows.append([_btn(f"Mark watched · {name}", f"watched:{row.id}")])
    elif row.status == WatchStatus.want:
        rows.append([_btn(f"Start · {name}", f"startwatch:{row.id}")])
    rows.append([_btn(f"Remove · {name}", f"rmask:{row.id}")])
    return rows


def _after_save_keyboard(row: UserTitle | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if row and row.status == WatchStatus.watching:
        name = _short_name(row.title.title)
        if row.title.media_type == MediaType.tv:
            rows.append(
                [
                    _btn(f"Next · {name}", f"next:{row.id}"),
                    _btn(f"Mark ep · {name}", f"watched:{row.id}"),
                ]
            )
        else:
            rows.append([_btn(f"Mark watched · {name}", f"watched:{row.id}")])
    rows.append(
        [
            InlineKeyboardButton("My list", callback_data="menu:list"),
            InlineKeyboardButton("Home", callback_data="menu:home"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _after_next_keyboard(row: UserTitle) -> InlineKeyboardMarkup:
    name = _short_name(row.title.title)
    return InlineKeyboardMarkup(
        [
            [_btn(f"Mark ep · {name}", f"watched:{row.id}")],
            [
                InlineKeyboardButton("My list", callback_data="menu:list"),
                InlineKeyboardButton("Home", callback_data="menu:home"),
            ],
        ]
    )


def _progress_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Start at S1E1", callback_data="progress:1:1")],
            [InlineKeyboardButton("Cancel", callback_data="menu:cancel")],
        ]
    )


async def _edit_or_reply(query, text: str, reply_markup=None, parse_mode=None) -> None:
    try:
        if query.message is None:
            try:
                await query.edit_message_caption(
                    caption=text[:1024],
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )
            except Exception:
                await query.edit_message_text(
                    text=text, reply_markup=reply_markup, parse_mode=parse_mode
                )
            return
        if query.message.photo:
            await query.edit_message_caption(
                caption=text[:1024], reply_markup=reply_markup, parse_mode=parse_mode
            )
        else:
            await query.edit_message_text(
                text=text, reply_markup=reply_markup, parse_mode=parse_mode
            )
    except Exception:
        logger.exception("Failed to edit callback message; sending a new one")
        bot = query.get_bot()
        chat_id = query.message.chat_id if query.message else query.from_user.id
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )


async def _reply(
    update: Update,
    text: str,
    reply_markup=None,
    via_callback: bool = False,
    parse_mode=None,
) -> None:
    if via_callback and update.callback_query:
        await _edit_or_reply(
            update.callback_query, text, reply_markup=reply_markup, parse_mode=parse_mode
        )
    else:
        await update.effective_message.reply_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )


def _parse_search_query(raw: str) -> tuple[str, str | None]:
    q = raw.strip()
    lower = q.lower()
    prefixes = (
        ("movie ", "movie"),
        ("movies ", "movie"),
        ("tv ", "tv"),
        ("show ", "tv"),
        ("shows ", "tv"),
        ("m:", "movie"),
        ("t:", "tv"),
    )
    for prefix, media_type in prefixes:
        if lower.startswith(prefix):
            return q[len(prefix) :].strip(), media_type
    return q, None


def _clear_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("pending_add", None)


# --- Commands -----------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>Sofar</b>\n"
        "Track what you watch. Know where you left off.\n\n"
        "<b>Search</b> — find a title\n"
        "<b>Continue</b> — what's next / mark an episode\n"
        "<b>My list</b> — Want · Watching · Watched"
    )
    await update.message.reply_text(
        text, reply_markup=_main_menu_keyboard(), parse_mode=ParseMode.HTML
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>Quick tips</b>\n\n"
        "• <b>Search</b> → type → tap a result → Want / Watching / Watched\n"
        "• Filter search: <code>movie dune</code> or <code>tv the bear</code>\n"
        "• <b>Continue</b> for what's next or mark an episode\n"
        "• Status words are always: Want · Watching · Watched"
    )
    await update.message.reply_text(
        text, reply_markup=_main_menu_keyboard(), parse_mode=ParseMode.HTML
    )


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await update.message.reply_text(
            "<b>Search</b>\n"
            "Tap Search, then type. Results update as you type.\n\n"
            "Filters: <code>movie …</code> or <code>tv …</code>",
            reply_markup=InlineKeyboardMarkup(
                [
                    [_search_button()],
                    [
                        InlineKeyboardButton(
                            "Movies only", switch_inline_query_current_chat="movie "
                        ),
                        InlineKeyboardButton(
                            "Shows only", switch_inline_query_current_chat="tv "
                        ),
                    ],
                    [InlineKeyboardButton("Home", callback_data="menu:home")],
                ]
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    q, media_type = _parse_search_query(query)
    tmdb: TmdbClient = context.application.bot_data["tmdb"]
    try:
        results = (
            tmdb.search(q, limit=8, media_type=media_type)
            if q
            else tmdb.trending(limit=8, media_type=media_type)
        )
    except Exception:
        logger.exception("TMDB search failed")
        await update.message.reply_text("Search failed. Try again in a moment.")
        return

    if not results:
        await update.message.reply_text(
            f'Nothing found for "{html.escape(query)}".',
            reply_markup=InlineKeyboardMarkup(
                [[_search_button()], [InlineKeyboardButton("Home", callback_data="menu:home")]]
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                _title_plain(r.title, r.year, r.media_type)[:64],
                callback_data=f"pick:{r.media_type}:{r.tmdb_id}",
            )
        ]
        for r in results
    ]
    buttons.append(
        [_search_button(query), InlineKeyboardButton("Home", callback_data="menu:home")]
    )
    await update.message.reply_text(
        f'Results for "<i>{html.escape(query)}</i>":',
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
    )


# --- Live inline search -------------------------------------------------------


def _inline_caption(r: SearchResult) -> str:
    overview = r.overview or "No overview."
    caption = (
        f"{_title_html(r.title, r.year, r.media_type)}\n\n"
        f"{html.escape(overview)}\n\n"
        "Add as:"
    )
    return caption[:1024]


def _result_to_inline(r: SearchResult, tmdb: TmdbClient) -> InlineQueryResultArticle:
    year_bit = f" ({r.year})" if r.year else ""
    kind = _kind_label(r.media_type)
    title = f"{r.title}{year_bit}"
    overview = (r.overview or "No overview.").replace("\n", " ")
    if len(overview) > 100:
        overview = overview[:97] + "..."
    description = f"{kind} · {overview}"
    thumb = tmdb.poster_url(r.poster_path, size="w185")

    return InlineQueryResultArticle(
        id=f"{r.media_type}:{r.tmdb_id}",
        title=title[:64],
        description=description[:120],
        thumbnail_url=thumb,
        input_message_content=InputTextMessageContent(
            _inline_caption(r), parse_mode=ParseMode.HTML
        ),
        reply_markup=_status_keyboard(r.media_type, r.tmdb_id),
    )


async def on_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    inline = update.inline_query
    assert inline is not None
    raw = inline.query or ""
    q, media_type = _parse_search_query(raw)
    tmdb: TmdbClient = context.application.bot_data["tmdb"]

    try:
        if len(q) < 1:
            results = tmdb.trending(limit=10, media_type=media_type)
        else:
            results = tmdb.search(q, limit=10, media_type=media_type)
    except Exception:
        logger.exception("Inline TMDB search failed")
        await inline.answer(
            [],
            cache_time=5,
            is_personal=True,
            switch_pm_text="Search failed - open Sofar",
            switch_pm_parameter="start",
        )
        return

    await inline.answer(
        [_result_to_inline(r, tmdb) for r in results],
        cache_time=2,
        is_personal=True,
    )


# --- Menus & library ----------------------------------------------------------


async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "cancel":
        _clear_pending(context)
        await _edit_or_reply(
            query,
            "Cancelled.",
            reply_markup=_main_menu_keyboard(),
        )
        return
    if action == "home":
        await _edit_or_reply(
            query,
            "<b>Sofar</b>\nSearch · Continue · My list",
            reply_markup=_main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return
    if action == "list":
        await _send_library(update, context, status=None, via_callback=True)
        return
    if action == "continue":
        await _continue_menu(update, context, via_callback=True)
        return


async def _continue_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, via_callback: bool = False
) -> None:
    """Continue = what's next or mark episode for Watching titles."""
    telegram_id, display_name = _user_meta(update)
    db = SessionLocal()
    try:
        user = services.get_or_create_user(db, telegram_id, display_name)
        rows = services.list_library(db, user, status=WatchStatus.watching, limit=12)
        if not rows:
            await _reply(
                update,
                "<b>Continue</b>\nNothing in Watching yet.\nSearch for a show to start.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [_search_button()],
                        [InlineKeyboardButton("Home", callback_data="menu:home")],
                    ]
                ),
                via_callback=via_callback,
                parse_mode=ParseMode.HTML,
            )
            return

        if len(rows) == 1:
            row = rows[0]
            name = _short_name(row.title.title)
            text = (
                f"<b>Continue</b>\n"
                f"{_title_html(row.title.title, row.title.year, row.title.media_type)}"
                f"{html.escape(_progress_bit(row))}"
            )
            if row.title.media_type == MediaType.tv:
                markup = InlineKeyboardMarkup(
                    [
                        [
                            _btn(f"Next · {name}", f"next:{row.id}"),
                            _btn(f"Mark ep · {name}", f"watched:{row.id}"),
                        ],
                        [InlineKeyboardButton("Home", callback_data="menu:home")],
                    ]
                )
            else:
                markup = InlineKeyboardMarkup(
                    [
                        [_btn(f"Mark watched · {name}", f"watched:{row.id}")],
                        [InlineKeyboardButton("Home", callback_data="menu:home")],
                    ]
                )
            await _reply(
                update, text, reply_markup=markup, via_callback=via_callback, parse_mode=ParseMode.HTML
            )
            return

        buttons: list[list[InlineKeyboardButton]] = []
        for row in rows:
            name = _short_name(row.title.title, 22)
            prog = _progress_bit(row)
            if row.title.media_type == MediaType.tv:
                buttons.append(
                    [
                        _btn(f"Next · {name}{prog}", f"next:{row.id}"),
                        _btn(f"Mark ep · {name}", f"watched:{row.id}"),
                    ]
                )
            else:
                buttons.append([_btn(f"Mark watched · {name}", f"watched:{row.id}")])
        buttons.append([InlineKeyboardButton("Home", callback_data="menu:home")])
        await _reply(
            update,
            "<b>Continue</b>\nPick a title:",
            reply_markup=InlineKeyboardMarkup(buttons),
            via_callback=via_callback,
            parse_mode=ParseMode.HTML,
        )
    finally:
        db.close()


async def on_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3:
        return
    _, media_type, tmdb_id_s = parts
    tmdb_id = int(tmdb_id_s)
    tmdb: TmdbClient = context.application.bot_data["tmdb"]
    detail = tmdb.get_title(media_type, tmdb_id)
    overview = detail.overview or "No overview."
    caption = (
        f"{_title_html(detail.title, detail.year, media_type)}\n\n"
        f"{html.escape(overview)}\n\n"
        "Add as:"
    )
    markup = _status_keyboard(media_type, tmdb_id)
    poster = tmdb.poster_url(detail.poster_path)
    if poster and query.message:
        try:
            await query.message.reply_photo(
                photo=poster,
                caption=caption[:1024],
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
            )
            await query.edit_message_reply_markup(reply_markup=None)
            return
        except Exception:
            logger.exception("Failed to send poster")
    await _edit_or_reply(query, caption, reply_markup=markup, parse_mode=ParseMode.HTML)


async def on_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 4:
        return
    _, status_s, media_type, tmdb_id_s = parts
    status = WatchStatus(status_s)
    tmdb_id = int(tmdb_id_s)
    telegram_id, display_name = _user_meta(update)
    tmdb: TmdbClient = context.application.bot_data["tmdb"]

    db = SessionLocal()
    try:
        user = services.get_or_create_user(db, telegram_id, display_name)
        title = services.upsert_title_from_tmdb(db, tmdb, media_type, tmdb_id)

        if status == WatchStatus.watching and title.media_type == MediaType.tv:
            context.user_data["pending_add"] = {
                "tmdb_id": tmdb_id,
                "media_type": media_type,
            }
            await _edit_or_reply(
                query,
                f"Starting <b>{html.escape(title.title)}</b>.\n"
                "Tap <b>Start at S1E1</b>, or send where you are "
                "(e.g. <code>S2E4</code>).",
                reply_markup=_progress_keyboard(),
                parse_mode=ParseMode.HTML,
            )
            return

        row = services.add_or_update_library(db, user, title, status)
        row = services.get_library_row(db, user, row.id)
        label = STATUS_LABELS[status]
        text = (
            f"Saved {_title_html(title.title, title.year, title.media_type)}\n"
            f"Status: <b>{html.escape(label)}</b>"
        )
        await _edit_or_reply(
            query, text, reply_markup=_after_save_keyboard(row), parse_mode=ParseMode.HTML
        )
    finally:
        db.close()


def _parse_progress(raw: str) -> tuple[int | None, int | None]:
    m = re.match(r"^[sS]?(\d+)[eE\s]+(\d+)$", raw.replace(",", " "))
    if m:
        return int(m.group(1)), int(m.group(2))
    parts = raw.split()
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    return None, None


async def on_progress_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, season_s, episode_s = query.data.split(":")
    await _finish_watching_add(
        update, context, season=int(season_s), episode=int(episode_s), via_callback=True
    )


async def progress_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "pending_add" not in context.user_data:
        return
    raw = (update.message.text or "").strip()
    season, episode = _parse_progress(raw)
    if season is None or episode is None:
        await update.message.reply_text(
            "Send <code>S2E4</code> or <code>2 4</code>, tap Start at S1E1, or Cancel.",
            reply_markup=_progress_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return
    await _finish_watching_add(
        update, context, season=season, episode=episode, via_callback=False
    )


async def _finish_watching_add(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    season: int,
    episode: int,
    via_callback: bool,
) -> None:
    pending = context.user_data.pop("pending_add", None)
    if not pending:
        await _reply(
            update,
            "Nothing pending - tap Search to add a show.",
            reply_markup=_main_menu_keyboard(),
            via_callback=via_callback,
        )
        return

    telegram_id, display_name = _user_meta(update)
    tmdb: TmdbClient = context.application.bot_data["tmdb"]
    db = SessionLocal()
    try:
        user = services.get_or_create_user(db, telegram_id, display_name)
        title = services.upsert_title_from_tmdb(
            db, tmdb, pending["media_type"], pending["tmdb_id"]
        )
        row = services.add_or_update_library(
            db,
            user,
            title,
            WatchStatus.watching,
            current_season=season,
            current_episode=episode,
        )
        row = services.get_library_row(db, user, row.id)
        text = (
            f"Saved {_title_html(title.title, title.year, title.media_type)}\n"
            f"Watching at <b>S{season}E{episode}</b>"
        )
        markup = _after_save_keyboard(row)
    finally:
        db.close()

    await _reply(
        update, text, reply_markup=markup, via_callback=via_callback, parse_mode=ParseMode.HTML
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _clear_pending(context)
    await update.message.reply_text("Cancelled.", reply_markup=_main_menu_keyboard())


async def _send_library(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    status: WatchStatus | None,
    via_callback: bool = False,
) -> None:
    telegram_id, display_name = _user_meta(update)
    db = SessionLocal()
    try:
        user = services.get_or_create_user(db, telegram_id, display_name)
        rows = services.list_library(db, user, status=status, limit=8, offset=0)
        header = STATUS_LABELS[status] if status else "Your list"
        buttons = _list_filter_keyboard(status)

        if not rows:
            text = (
                f"<b>{html.escape(header)}</b>\n"
                "Empty for now.\nTap Search to add something."
            )
            buttons.append([_search_button()])
            buttons.append([InlineKeyboardButton("Home", callback_data="menu:home")])
            await _reply(
                update,
                text,
                reply_markup=InlineKeyboardMarkup(buttons),
                via_callback=via_callback,
                parse_mode=ParseMode.HTML,
            )
            return

        lines = [f"<b>{html.escape(header)}</b>"]
        for row in rows:
            lines.append(
                f"· {_title_html(row.title.title, row.title.year, row.title.media_type)}"
                f"{html.escape(_progress_bit(row))} · {STATUS_LABELS[row.status]}"
            )
            buttons.extend(_item_actions(row))
        buttons.append(
            [
                _search_button(),
                InlineKeyboardButton("Home", callback_data="menu:home"),
            ]
        )
        await _reply(
            update,
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(buttons),
            via_callback=via_callback,
            parse_mode=ParseMode.HTML,
        )
    finally:
        db.close()


async def on_list_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    key = query.data.split(":", 1)[1]
    status = None if key == "all" else WatchStatus(key)
    await _send_library(update, context, status=status, via_callback=True)


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = None
    if context.args:
        key = context.args[0].lower().replace("-", "").replace("_", "")
        mapping = {
            "want": WatchStatus.want,
            "wanttowatch": WatchStatus.want,
            "watching": WatchStatus.watching,
            "watched": WatchStatus.watched,
        }
        status = mapping.get(key)
        if status is None:
            await update.message.reply_text(
                "Pick a filter:",
                reply_markup=InlineKeyboardMarkup(_list_filter_keyboard()),
            )
            return
    await _send_library(update, context, status=status, via_callback=False)


async def watching_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_library(update, context, status=WatchStatus.watching, via_callback=False)


async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _continue_menu(update, context, via_callback=False)


async def watched_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _continue_menu(update, context, via_callback=False)


async def on_next_or_watched(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action, id_s = query.data.split(":", 1)
    await _handle_watching_action(update, context, int(id_s), action, via_callback=True)


async def on_start_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_title_id = int(query.data.split(":")[1])
    telegram_id, display_name = _user_meta(update)
    tmdb: TmdbClient = context.application.bot_data["tmdb"]
    db = SessionLocal()
    try:
        user = services.get_or_create_user(db, telegram_id, display_name)
        row = services.get_library_row(db, user, user_title_id)
        if not row:
            await _edit_or_reply(query, "Title not found.", reply_markup=_main_menu_keyboard())
            return
        if row.title.media_type == MediaType.tv:
            context.user_data["pending_add"] = {
                "tmdb_id": row.title.tmdb_id,
                "media_type": "tv",
            }
            await _edit_or_reply(
                query,
                f"Starting <b>{html.escape(row.title.title)}</b>.\n"
                "Tap <b>Start at S1E1</b>, or send where you are "
                "(e.g. <code>S2E4</code>).",
                reply_markup=_progress_keyboard(),
                parse_mode=ParseMode.HTML,
            )
            return
        row = services.add_or_update_library(db, user, row.title, WatchStatus.watching)
        row = services.get_library_row(db, user, row.id)
        await _edit_or_reply(
            query,
            f"Now watching {_title_html(row.title.title, row.title.year, row.title.media_type)}",
            reply_markup=_after_save_keyboard(row),
            parse_mode=ParseMode.HTML,
        )
    finally:
        db.close()


async def _handle_watching_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_title_id: int,
    action: str,
    via_callback: bool = False,
) -> None:
    telegram_id, display_name = _user_meta(update)
    tmdb: TmdbClient = context.application.bot_data["tmdb"]
    db = SessionLocal()
    try:
        user = services.get_or_create_user(db, telegram_id, display_name)
        row = services.get_library_row(db, user, user_title_id)
        markup = _main_menu_keyboard()
        parse_mode = ParseMode.HTML
        if not row:
            text = "Title not found."
            parse_mode = None
        elif action == "next":
            if row.title.media_type == MediaType.movie:
                name = _short_name(row.title.title)
                text = f"Next: finish <b>{html.escape(row.title.title)}</b>"
                markup = InlineKeyboardMarkup(
                    [
                        [_btn(f"Mark watched · {name}", f"watched:{row.id}")],
                        [InlineKeyboardButton("Home", callback_data="menu:home")],
                    ]
                )
            else:
                s = row.current_season or 1
                e = row.current_episode or 1
                ep = tmdb.get_episode(row.title.tmdb_id, s, e)
                name = f" - {html.escape(ep.name)}" if ep and ep.name else ""
                text = (
                    f"<b>Next up</b>\n"
                    f"{html.escape(row.title.title)} · <b>S{s}E{e}</b>{name}"
                )
                markup = _after_next_keyboard(row)
        else:
            _, plain = services.mark_episode_watched(db, tmdb, user, user_title_id)
            row = services.get_library_row(db, user, user_title_id)
            text = html.escape(plain)
            markup = _after_save_keyboard(row)
    finally:
        db.close()

    await _reply(
        update, text, reply_markup=markup, via_callback=via_callback, parse_mode=parse_mode
    )


async def on_remove_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_title_id = int(query.data.split(":")[1])
    telegram_id, display_name = _user_meta(update)
    db = SessionLocal()
    try:
        user = services.get_or_create_user(db, telegram_id, display_name)
        row = services.get_library_row(db, user, user_title_id)
        if not row:
            await _edit_or_reply(query, "Already gone.", reply_markup=_main_menu_keyboard())
            return
        name = row.title.title
        short = _short_name(name)
        await _edit_or_reply(
            query,
            f"Remove <b>{html.escape(name)}</b> from your list?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        _btn(f"Remove · {short}", f"rm:{row.id}"),
                        InlineKeyboardButton("Keep", callback_data="menu:list"),
                    ]
                ]
            ),
            parse_mode=ParseMode.HTML,
        )
    finally:
        db.close()


async def on_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_title_id = int(query.data.split(":")[1])
    telegram_id, display_name = _user_meta(update)
    db = SessionLocal()
    try:
        user = services.get_or_create_user(db, telegram_id, display_name)
        row = services.get_library_row(db, user, user_title_id)
        name = row.title.title if row else "Title"
        ok = services.remove_from_library(db, user, user_title_id)
        text = f"Removed <b>{html.escape(name)}</b>." if ok else "Already gone."
        await _edit_or_reply(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("My list", callback_data="menu:list")],
                    [InlineKeyboardButton("Home", callback_data="menu:home")],
                ]
            ),
            parse_mode=ParseMode.HTML,
        )
    finally:
        db.close()


async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_library(update, context, status=None, via_callback=False)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Bot commands registered with Telegram")


def build_application() -> Application:
    settings = get_settings()
    init_db()
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    app.bot_data["tmdb"] = TmdbClient(settings)

    app.add_handler(InlineQueryHandler(on_inline_query))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("watching", watching_cmd))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CommandHandler("watched", watched_cmd))
    app.add_handler(CommandHandler("remove", remove_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(on_menu, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(on_list_filter, pattern=r"^list:"))
    app.add_handler(CallbackQueryHandler(on_pick, pattern=r"^pick:"))
    app.add_handler(CallbackQueryHandler(on_status, pattern=r"^status:"))
    app.add_handler(CallbackQueryHandler(on_progress_button, pattern=r"^progress:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(on_start_watch, pattern=r"^startwatch:\d+$"))
    app.add_handler(CallbackQueryHandler(on_next_or_watched, pattern=r"^(next|watched):\d+$"))
    app.add_handler(CallbackQueryHandler(on_remove_ask, pattern=r"^rmask:\d+$"))
    app.add_handler(CallbackQueryHandler(on_remove, pattern=r"^rm:\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, progress_text))
    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    app = build_application()
    logger.info("Sofar bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
