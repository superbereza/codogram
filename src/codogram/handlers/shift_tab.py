"""Shift+Tab command handler."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from ..tmux import TmuxSession
from ..services.session_state import SessionStateService

router = Router(name="shift_tab")
service = SessionStateService()


def _get_tmux_for_context(chat_id: int, thread_id: int | None) -> TmuxSession | None:
    """Get TmuxSession for current chat/thread context."""
    project = project_manager.get_by_chat(chat_id)
    if not project:
        return None

    if thread_id and project.threads:
        thread = project.threads.get(thread_id)
        if thread:
            tmux_name = thread.get_tmux_session(project.project_name)
            return TmuxSession(tmux_name, thread.worktree_path or project.cwd)

    if project.tmux_session:
        return TmuxSession(project.tmux_session, project.cwd)

    return None


def _format_mode(mode: str | None) -> str:
    """Format approval mode for display."""
    if mode == "accept edits":
        return "⏵⏵ accept edits on"
    elif mode == "plan mode":
        return "⏸ plan mode on"
    else:
        return "default mode on"


@router.message(Command("shift_tab"))
async def cmd_shift_tab(message: Message, telegram_queue: TelegramQueue):
    """Send Shift+Tab to cycle Claude approval mode."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    tmux = _get_tmux_for_context(chat_id, thread_id)
    if not tmux:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    result = service.cycle_approval_mode(tmux)

    if not result.success:
        await telegram_queue.reply(message, result.error)
        return

    mode_text = _format_mode(result.new_mode)
    await telegram_queue.reply(message, mode_text)
