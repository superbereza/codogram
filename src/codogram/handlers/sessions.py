"""Session management: /new, /clear, /esc, /resume."""
import asyncio
import time

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from .. import strings
from ..session_manager import project_manager
from ..project_launcher import is_tmux_session_exists
from ..tmux import TmuxSession
from ..logging_config import logger
from ..telegram_queue import TelegramQueue
from .common import require_tmux_exists, require_claude_ready

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


@router.message(Command("new"))
async def cmd_new(message: Message, telegram_queue: TelegramQueue):
    """Start new Claude session in current thread."""
    if not await require_claude_ready(message, telegram_queue):
        return
    tmux = await _send_session_command(message, telegram_queue, "/new", strings.NEW_SESSION)
    if tmux:
        await _wait_for_claude_ready(tmux, telegram_queue, message.chat.id, message.message_thread_id)


@router.message(Command("clear"))
async def cmd_clear(message: Message, telegram_queue: TelegramQueue):
    """Clear Claude session and start fresh."""
    if not await require_tmux_exists(message, telegram_queue):
        return
    tmux = await _send_session_command(message, telegram_queue, "/clear", strings.CLEAR_SESSION)
    if tmux:
        await _wait_for_claude_ready(tmux, telegram_queue, message.chat.id, message.message_thread_id)


@router.message(Command("esc"))
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


@router.message(Command("resume"))
async def cmd_resume(message: Message, telegram_queue: TelegramQueue):
    """Handle /resume command - not supported in multi-session mode."""
    thread_id = message.message_thread_id
    if thread_id is not None:
        # In a topic - resume not supported
        await telegram_queue.reply(message, strings.RESUME_NOT_SUPPORTED_MULTI)
    else:
        # In private/general - just inform
        await telegram_queue.reply(message, strings.RESUME_NOT_SUPPORTED)
