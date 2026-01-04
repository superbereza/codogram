"""Session management: /new, /clear, /esc, /resume."""
import time

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..session_manager import project_manager
from ..project_launcher import is_tmux_session_exists
from ..tmux import TmuxSession
from ..logging_config import logger
from ..telegram_queue import TelegramQueue

router = Router(name="sessions")


async def _send_session_command(
    message: Message, telegram_queue: TelegramQueue, command: str, status_text: str
) -> bool:
    """Common logic for /new and /clear commands.

    Returns True if command was sent successfully, False otherwise.
    """
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, "Project not registered. Use /start")
        return False

    thread_id = message.message_thread_id
    thread = project.threads.get(thread_id)
    if not thread:
        await telegram_queue.reply(message, "Thread not found. Use /start")
        return False

    tmux_name = thread.get_tmux_session(project.project_name)

    if not is_tmux_session_exists(tmux_name):
        await telegram_queue.reply(message, "tmux session not found. Start Claude in terminal.")
        return False

    # Mark thread as awaiting new session
    thread.awaiting_new_session = True
    thread.start_requested_at = time.time()
    thread.last_sent_message = None
    project_manager._save()

    # Send command to tmux
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_keys(command)

    await telegram_queue.reply(message, status_text)
    return True


@router.message(Command("new"))
async def cmd_new(message: Message, telegram_queue: TelegramQueue):
    """Start new Claude session in current thread."""
    await _send_session_command(message, telegram_queue, "/new", "`[~]` Creating new session...")


@router.message(Command("clear"))
async def cmd_clear(message: Message, telegram_queue: TelegramQueue):
    """Clear Claude session and start fresh."""
    await _send_session_command(message, telegram_queue, "/clear", "`[~]` Clearing session...")


@router.message(Command("esc"))
async def cmd_esc(message: Message):
    """Send Escape to current thread's tmux."""
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
        await telegram_queue.reply(
            message,
            "`[!]` /resume not supported in multi-session mode.\n"
            "Use /thread_create for a new thread.",
        )
    else:
        # In private/general - just inform
        await telegram_queue.reply(
            message,
            "`[!]` /resume not supported.\n"
            "Use /start to connect to existing session.",
        )
