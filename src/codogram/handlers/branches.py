"""Branch aliases - redirect to /new_chat."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from .. import strings
from ..telegram.queue import TelegramQueue
from .new_chat import cmd_new_chat
from .common import CommandStrict

router = Router(name="branches")


@router.message(Command("branch", "branch_create", ignore_case=True), CommandStrict())
async def cmd_branch(message: Message, telegram_queue: TelegramQueue):
    """Alias for /new_chat."""
    await cmd_new_chat(message, telegram_queue)


@router.message(Command("branch_finish", ignore_case=True), CommandStrict())
async def cmd_branch_finish(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish_chat."""
    await telegram_queue.reply(message, strings.BRANCH_FINISH_USE_FINISH)
