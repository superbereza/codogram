"""Whisper usage statistics handler - admin DM only."""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from ..services.whisper_stats import WhisperStatsService
from ..telegram.queue import TelegramQueue
from .. import strings

router = Router(name="whisper_stats")

_stats_service = WhisperStatsService()

PERIOD_LABELS = {
    "7d": "last 7 days",
    "30d": "last 30 days",
    "all": "all time",
}


def _build_keyboard(view: str, period: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for stats message."""
    # Toggle button
    if view == "users":
        toggle_text = strings.WHISPER_STATS_BTN_PROJECTS
        toggle_view = "projects"
    else:
        toggle_text = strings.WHISPER_STATS_BTN_USERS
        toggle_view = "users"

    # Period buttons
    periods = ["7d", "30d", "all"]
    period_buttons = []
    for p in periods:
        label = getattr(strings, f"WHISPER_STATS_PERIOD_{p.upper()}")
        if p == period:
            label = f"{label} ✓"
        period_buttons.append(
            InlineKeyboardButton(text=label, callback_data=f"ws:{view}:{p}")
        )

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"ws:{toggle_view}:{period}")],
        period_buttons,
    ])


def _format_stats(view: str, period: str) -> str:
    """Format stats message text."""
    result = _stats_service.get_stats(view, period)

    lines = [strings.WHISPER_STATS_TITLE.format(period=PERIOD_LABELS[period]), ""]

    if view == "users":
        lines.append(strings.WHISPER_STATS_BY_USERS)
    else:
        lines.append(strings.WHISPER_STATS_BY_PROJECTS)

    if not result.entries:
        lines.append(strings.WHISPER_STATS_EMPTY)
    else:
        for entry in result.entries:
            lines.append(strings.WHISPER_STATS_ENTRY.format(
                name=entry.name,
                cost=entry.cost_usd,
                count=entry.count,
            ))

    lines.append("")
    lines.append(strings.WHISPER_STATS_TOTAL.format(
        cost=result.total_cost,
        count=result.total_count,
    ))

    return "\n".join(lines)


@router.message(Command("whisper_stats"), F.chat.type == "private")
async def cmd_whisper_stats(message: Message, telegram_queue: TelegramQueue):
    """Show whisper usage statistics."""
    view = "users"
    period = "7d"

    text = _format_stats(view, period)
    keyboard = _build_keyboard(view, period)

    await telegram_queue.reply(message, text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("ws:"))
async def on_stats_callback(callback: CallbackQuery):
    """Handle stats view/period toggle."""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Invalid callback")
        return

    _, view, period = parts

    if view not in ("users", "projects") or period not in ("7d", "30d", "all"):
        await callback.answer("Invalid parameters")
        return

    text = _format_stats(view, period)
    keyboard = _build_keyboard(view, period)

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
