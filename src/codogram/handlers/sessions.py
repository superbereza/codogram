"""Session management: /clear_context, /esc."""
import asyncio
import time

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from .. import strings
from ..core.session_manager import project_manager
from ..tmux.launcher import is_tmux_session_exists
from ..tmux.session import TmuxSession
from ..state import active_ask_prompts, permission_messages, ask_options_state
from ..logging_config import logger
from ..telegram.queue import TelegramQueue
from .common import require_tmux_exists, require_claude_ready, normalize_thread_id

router = Router(name="sessions")

# Timeout for waiting Claude ready (seconds)
CLAUDE_READY_TIMEOUT = 60


async def _send_session_command(
    message: Message, telegram_queue: TelegramQueue, command: str, status_text: str
) -> TmuxSession | None:
    """Common logic for /new and /clear commands.

    Returns TmuxSession if command was sent successfully, None otherwise.
    """
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, strings.PROJECT_NOT_REGISTERED)
        return None

    thread_id = message.message_thread_id
    thread = project.threads.get(thread_id)
    if not thread:
        await telegram_queue.reply(message, strings.THREAD_NOT_FOUND_START)
        return None

    tmux_name = thread.get_tmux_session(project.project_name)

    if not is_tmux_session_exists(tmux_name):
        await telegram_queue.reply(message, strings.CLAUDE_TMUX_NOT_FOUND)
        return None

    # Cancel old watcher task so new one can be created after rebinding
    # Without this, poll_for_session_thread sees existing task and skips creating new watcher
    if thread.watcher_task:
        thread.watcher_task.cancel()
        thread.watcher_task = None

    # Mark thread as awaiting new session
    thread.awaiting_new_session = True
    thread.start_requested_at = time.time()
    thread.last_sent_message = None
    thread.session_id = None  # Clear so next message triggers rebinding
    project_manager._save()

    # Send command to tmux
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send(command)

    await telegram_queue.reply(message, status_text)
    return tmux


async def _wait_for_claude_ready(
    tmux: TmuxSession, telegram_queue: TelegramQueue, chat_id: int, thread_id: int | None
) -> None:
    """Poll until Claude is ready, then send confirmation message."""
    start_time = time.time()

    while time.time() - start_time < CLAUDE_READY_TIMEOUT:
        if tmux.is_claude_ready():
            await telegram_queue.send(
                chat_id,
                strings.LAUNCH_READY,
                thread_id=thread_id,
            )
            return
        await asyncio.sleep(0.5)

    # Timeout - don't send anything, user will see when they interact


@router.message(Command("clear_context", "clear", "new", ignore_case=True))
async def cmd_clear_context(message: Message, telegram_queue: TelegramQueue):
    """Clear Claude context and start fresh."""
    if not await require_tmux_exists(message, telegram_queue):
        return
    tmux = await _send_session_command(message, telegram_queue, "/clear", strings.CLEAR_SESSION)
    if tmux:
        await _wait_for_claude_ready(tmux, telegram_queue, message.chat.id, message.message_thread_id)


@router.message(Command("esc", ignore_case=True))
async def cmd_esc(message: Message, telegram_queue: TelegramQueue):
    """Send Escape to current thread's tmux."""
    if not await require_tmux_exists(message, telegram_queue):
        return
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        return

    # Get correct thread (topic or main)
    thread = project.threads.get(thread_id)
    if not thread:
        return

    if not project.cwd:
        logger.error(f"esc: project {project.project_name} has no cwd")
        return

    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_key("Escape")

    # Delete active AskUserQuestion messages if any
    normalized_thread_id = normalize_thread_id(message.chat, thread_id)
    key = (chat_id, normalized_thread_id)
    kb_msg_id = active_ask_prompts.get(key)
    if kb_msg_id:
        related_ids = permission_messages.get(kb_msg_id, [])
        for msg_id in related_ids:
            try:
                await message.bot.delete_message(chat_id, msg_id)
            except Exception:
                pass
        try:
            await message.bot.delete_message(chat_id, kb_msg_id)
        except Exception:
            pass
        permission_messages.pop(kb_msg_id, None)
        ask_options_state.pop(kb_msg_id, None)
        active_ask_prompts.pop(key, None)


@router.message(Command("resume", ignore_case=True))
async def cmd_resume(message: Message, telegram_queue: TelegramQueue):
    """Handle /resume command - not supported in multi-session mode."""
    thread_id = message.message_thread_id
    if thread_id is not None:
        # In a topic - resume not supported
        await telegram_queue.reply(message, strings.RESUME_NOT_SUPPORTED_MULTI)
    else:
        # In private/general - just inform
        await telegram_queue.reply(message, strings.RESUME_NOT_SUPPORTED)
