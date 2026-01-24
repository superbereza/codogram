# src/codogram/handlers/start/helpers.py
"""Helper functions for start flow handlers."""
from aiogram import Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from ... import strings
from ...services.menu import register_menu_for_chat
from ...telegram.queue import TelegramQueue


async def register_chat_menu(bot: Bot, chat) -> None:
    """Register scope-based menu for chat."""
    await register_menu_for_chat(bot, chat.id, is_forum=chat.is_forum or False)


async def get_state_data(
    state: FSMContext,
    callback: CallbackQuery,
    queue: TelegramQueue,
    *keys: str,
) -> dict | None:
    """Get required FSM data, show error if missing."""
    data = await state.get_data()
    missing = [k for k in keys if k not in data]
    if missing:
        await state.clear()
        await queue.edit(callback.message, strings.START_SESSION_EXPIRED, parse_mode=None)
        await callback.answer()
        return None
    return data


async def get_state_data_msg(
    state: FSMContext,
    message: Message,
    queue: TelegramQueue,
    *keys: str,
) -> dict | None:
    """Get required FSM data for message handlers."""
    data = await state.get_data()
    missing = [k for k in keys if k not in data]
    if missing:
        await state.clear()
        await queue.reply(message, strings.START_SESSION_EXPIRED)
        return None
    return data


def parse_callback_data(data: str, expected_parts: int) -> tuple | None:
    """Safely parse callback data.

    Returns tuple of parts or None if invalid.
    BUG FIX: Previously crashed on malformed callback data.
    """
    parts = data.split(":")
    if len(parts) < expected_parts:
        return None
    return tuple(parts)


def parse_thread_id(value: str) -> int | None:
    """Parse thread_id from callback data.

    BUG FIX: Previously crashed on non-numeric values.
    """
    if value == "None":
        return None
    try:
        return int(value)
    except ValueError:
        return None  # Invalid, will be handled by caller
