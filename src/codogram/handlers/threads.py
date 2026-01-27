"""Thread aliases - redirect to /new_chat."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..telegram.queue import TelegramQueue
from .new_chat import cmd_new_chat
from .common import CommandStrict

router = Router(name="threads")


@router.message(Command("thread", "thread_create", ignore_case=True), CommandStrict())
async def cmd_thread(message: Message, telegram_queue: TelegramQueue):
    """Alias for /new_chat."""
    await cmd_new_chat(message, telegram_queue)


@router.message(Command("thread_delete", ignore_case=True), CommandStrict())
async def cmd_thread_delete(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish_chat."""
    await telegram_queue.reply(message, "`[i]` Use /finish_chat to archive chats")
