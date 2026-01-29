# src/codogram/handlers/settings/reset.py
"""Reset to default command handler."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.enums import ChatType

from ...core.session_manager import project_manager
from ...telegram.queue import TelegramQueue
from ... import strings
from ...config import settings

router = Router(name="settings_reset")


def _is_admin(message: Message) -> bool:
    """Check if user is admin."""
    return message.from_user.id in settings.get_admin_ids()


def _reset_thread_to_defaults(thread) -> None:
    """Clear all setting overrides in thread."""
    thread.auto_accept = None
    thread.response_mode = None
    thread.display_mode = None
    thread.line_limit = None
    thread.display_bullet = None
    thread.display_thinking_text = None
    thread.working_status = None
    thread.feat_suggestions = None
    thread.feat_avatar_pack = None


def _reset_all_threads() -> int:
    """Reset all threads in all projects. Returns count of reset threads."""
    count = 0
    for project in project_manager.projects.values():
        for thread in project.threads.values():
            _reset_thread_to_defaults(thread)
            count += 1
    project_manager._save()
    return count


@router.message(Command("reset_to_default", ignore_case=True), F.chat.type == ChatType.PRIVATE)
async def cmd_reset_to_default_dm(message: Message, telegram_queue: TelegramQueue):
    """Reset all threads to global defaults (DM version)."""
    if not _is_admin(message):
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes", callback_data="reset:all:yes"),
            InlineKeyboardButton(text="No", callback_data="reset:all:no"),
        ]
    ])
    await telegram_queue.send(message.chat.id, strings.RESET_ALL_CONFIRM, reply_markup=kb)


@router.message(Command("reset_to_default", ignore_case=True))
async def cmd_reset_to_default(message: Message, telegram_queue: TelegramQueue):
    """Reset current thread to global defaults."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await telegram_queue.reply(message, "Thread not found.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes", callback_data=f"reset:thread:{thread_id}:yes"),
            InlineKeyboardButton(text="No", callback_data="reset:thread:no"),
        ]
    ])
    await telegram_queue.reply(message, strings.RESET_THREAD_CONFIRM, reply_markup=kb)


@router.callback_query(F.data == "reset:all:yes")
async def callback_reset_all_yes(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Confirm reset all threads."""
    count = _reset_all_threads()
    await telegram_queue.edit(callback.message, strings.RESET_ALL_DONE)
    await callback.answer(f"Reset {count} threads")


@router.callback_query(F.data == "reset:all:no")
async def callback_reset_all_no(callback: CallbackQuery):
    """Cancel reset all."""
    await callback.message.delete()
    await callback.answer("Cancelled")


@router.callback_query(F.data.startswith("reset:thread:") & F.data.endswith(":yes"))
async def callback_reset_thread_yes(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Confirm reset thread."""
    parts = callback.data.split(":")
    thread_id_str = parts[2]
    thread_id = None if thread_id_str == "None" else int(thread_id_str)

    chat_id = callback.message.chat.id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    _reset_thread_to_defaults(thread)
    project_manager._save()

    await telegram_queue.edit(callback.message, strings.RESET_THREAD_DONE)
    await callback.answer("Reset done")


@router.callback_query(F.data == "reset:thread:no")
async def callback_reset_thread_no(callback: CallbackQuery):
    """Cancel reset thread."""
    await callback.message.delete()
    await callback.answer("Cancelled")
