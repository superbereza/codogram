"""Common handlers and helpers used by multiple modules."""
from aiogram import Router, F
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery

from .. import strings


class CommandStrict(Filter):
    """Filter that only matches commands WITHOUT arguments.

    Use with Command filter to ensure '/settings' matches but '/settings text' doesn't.
    The message with args will fall through to on_unknown_command and be sent to Claude.

    Usage:
        @router.message(Command("settings"), CommandStrict())
    """

    async def __call__(self, message: Message) -> bool:
        if not message.text:
            return False
        # Split on whitespace - if more than one part, there are arguments
        parts = message.text.split(maxsplit=1)
        return len(parts) == 1
from ..telegram.queue import TelegramQueue
from ..core.session_manager import project_manager
from ..tmux.launcher import is_tmux_session_exists
from ..tmux.session import TmuxSession

router = Router(name="common")

# Flow state storage with (chat_id, thread_id) key
# Different threads in same chat don't conflict
_flow_state: dict[tuple[int, int | None], dict] = {}


def normalize_thread_id(chat, thread_id: int | None) -> int | None:
    """Normalize thread_id - ignore in non-forum chats.

    In forums, thread_id identifies the topic.
    In regular groups, thread_id may come from replies but should be ignored.
    """
    from ..logging_config import logger

    if not getattr(chat, 'is_forum', False):
        if thread_id is not None:
            logger.debug(f"normalize_thread_id: ignoring thread_id={thread_id} in non-forum chat={chat.id}")
        return None
    return thread_id


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


async def require_tmux_exists(
    message: Message, telegram_queue: TelegramQueue
) -> bool:
    """Check: project + cwd + tmux session exists.

    Use for commands that work during startup: /clear, /esc
    """
    project = project_manager.get_by_chat(message.chat.id)
    if not project or not project.cwd:
        await telegram_queue.reply(message, strings.PROJECT_NOT_READY)
        return False

    thread_id = normalize_thread_id(message.chat, message.message_thread_id)
    thread = project.threads.get(thread_id)
    if not thread:
        await telegram_queue.reply(message, strings.PROJECT_NOT_READY)
        return False

    tmux_name = thread.get_tmux_session(project.project_name)
    if not is_tmux_session_exists(tmux_name):
        await telegram_queue.reply(message, strings.CLAUDE_NOT_RUNNING.format(cwd=project.cwd))
        return False

    return True


async def require_claude_ready(
    message: Message, telegram_queue: TelegramQueue
) -> bool:
    """Strict check: project + cwd + tmux + Claude ready.

    Use for commands that need Claude running: /new, /thread, /branch, /finish
    """
    if not await require_tmux_exists(message, telegram_queue):
        return False

    # Additional check: Claude is ready (not starting)
    project = project_manager.get_by_chat(message.chat.id)
    thread_id = normalize_thread_id(message.chat, message.message_thread_id)
    thread = project.threads.get(thread_id)
    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)

    if not tmux.is_claude_ready():
        await telegram_queue.reply(message, strings.CLAUDE_STARTING)
        return False

    return True


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle generic cancel button."""
    chat_id = callback.message.chat.id
    thread_id = normalize_thread_id(callback.message.chat, callback.message.message_thread_id)
    clear_flow_state(chat_id, thread_id)
    await telegram_queue.edit(callback.message, strings.CANCELLED)
    await callback.answer()
