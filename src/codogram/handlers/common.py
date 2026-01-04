"""Common handlers and helpers used by multiple modules."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from ..telegram_queue import TelegramQueue

router = Router(name="common")

# State dict for thread_create flow (threads.py uses this)
# TODO: Migrate to aiogram FSM in future
_flow_state: dict[int, dict] = {}


async def require_forum_group(message: Message, telegram_queue: TelegramQueue) -> bool:
    """Check if message is from a forum group. Returns False and sends error if not."""
    if message.chat.type == "private":
        await telegram_queue.reply(message, "`[!]` This command requires a group with topics.")
        return False
    if not message.chat.is_forum:
        await telegram_queue.reply(message, "`[!]` Topics required. Enable in group settings -> Topics")
        return False
    return True


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle generic cancel button."""
    chat_id = callback.message.chat.id
    _flow_state.pop(chat_id, None)
    await telegram_queue.edit(callback.message, "Cancelled.")
    await callback.answer()
