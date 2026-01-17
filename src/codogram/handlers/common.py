"""Common handlers and helpers used by multiple modules."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from .. import strings
from ..telegram_queue import TelegramQueue

router = Router(name="common")

# Flow state storage with (chat_id, thread_id) key
# Different threads in same chat don't conflict
_flow_state: dict[tuple[int, int | None], dict] = {}


def get_flow_state(chat_id: int, thread_id: int | None) -> dict | None:
    """Get flow state for chat/thread."""
    return _flow_state.get((chat_id, thread_id))


def set_flow_state(chat_id: int, thread_id: int | None, state: dict) -> None:
    """Set flow state for chat/thread."""
    _flow_state[(chat_id, thread_id)] = state


def clear_flow_state(chat_id: int, thread_id: int | None) -> None:
    """Clear flow state for chat/thread."""
    _flow_state.pop((chat_id, thread_id), None)


def clear_flow_state_by_type(chat_id: int, thread_id: int | None, state_type: str) -> None:
    """Clear flow state only if it matches the given type."""
    key = (chat_id, thread_id)
    state = _flow_state.get(key)
    if state and state.get("type") == state_type:
        _flow_state.pop(key, None)


def has_flow_state(chat_id: int, thread_id: int | None) -> bool:
    """Check if chat/thread has flow state."""
    return (chat_id, thread_id) in _flow_state


async def require_forum_group(message: Message, telegram_queue: TelegramQueue) -> bool:
    """Check if message is from a forum group. Returns False and sends error if not."""
    if message.chat.type == "private":
        await telegram_queue.reply(message, strings.TOPICS_REQUIRED_GROUP)
        return False
    if not message.chat.is_forum:
        await telegram_queue.reply(message, strings.TOPICS_REQUIRED_ENABLE)
        return False
    return True


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle generic cancel button."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    clear_flow_state(chat_id, thread_id)
    await telegram_queue.edit(callback.message, strings.CANCELLED)
    await callback.answer()
