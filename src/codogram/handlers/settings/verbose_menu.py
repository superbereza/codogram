# src/codogram/handlers/settings/verbose_menu.py
"""Verbose mode detailed menu."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from ...core.session_manager import project_manager, get_thread_setting
from ...config import get_global_defaults
from ..common import CommandStrict
from ...telegram.queue import TelegramQueue
from ...telegram.keyboards.verbose_menu import verbose_menu_keyboard
from ...telegram.keyboards.settings import _short_id

router = Router(name="verbose_menu")

MODE_DESCRIPTIONS = {
    "show_all": "Full output without truncation",
    "lines": "Truncate tool output to {limit} lines",
    "headers": "Show tool headers only, no body",
    "current": "Single message, updated with each tool call",
    "silence": "Hide tool calls, show only Claude's text responses",
}


def _build_verbose_text(display_mode: str, line_limit: int) -> str:
    """Build verbose menu message text."""
    desc = MODE_DESCRIPTIONS.get(display_mode, "").format(limit=line_limit)
    return f"""**Verbose mode**
Current: {display_mode}{f' ({line_limit})' if display_mode == 'lines' else ''}
{desc}"""


@router.message(Command("verbose_mode", ignore_case=True), CommandStrict())
async def cmd_verbose_mode(message: Message, telegram_queue: TelegramQueue):
    """Show verbose mode menu."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    # Get current settings
    global_defaults = get_global_defaults()
    if thread:
        display_mode = get_thread_setting(thread, "display_mode", global_defaults)
        line_limit = get_thread_setting(thread, "line_limit", global_defaults)
        tmux_name = thread.get_tmux_session(project.project_name)
    else:
        display_mode = global_defaults["display_mode"]
        line_limit = global_defaults["line_limit"]
        tmux_name = f"claude-{project.project_name}"

    text = _build_verbose_text(display_mode, line_limit)
    kb = verbose_menu_keyboard(display_mode, line_limit, _short_id(tmux_name))

    await telegram_queue.reply(message, text, reply_markup=kb)


@router.callback_query(F.data.startswith("vm:"))
async def callback_verbose_menu(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle verbose menu button presses."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    short_id = parts[1]
    action = parts[2]

    # Find project and thread by short ID
    project = None
    thread = None
    tmux_name = None

    for p in project_manager.projects.values():
        for t in p.threads.values():
            t_tmux = t.get_tmux_session(p.project_name)
            if _short_id(t_tmux) == short_id:
                project = p
                thread = t
                tmux_name = t_tmux
                break
        if project:
            break
        p_tmux = f"claude-{p.project_name}"
        if _short_id(p_tmux) == short_id:
            project = p
            tmux_name = p_tmux
            break

    if not project:
        await callback.answer("Project not found")
        return

    if action == "close":
        await callback.message.delete()
        await callback.answer()
        return

    if action == "mode":
        if len(parts) < 4:
            await callback.answer("Invalid mode")
            return
        new_mode = parts[3]
        if thread:
            thread.display_mode = new_mode
        else:
            project.display_mode = new_mode
        project_manager._save()
        await callback.answer(f"Mode: {new_mode}")

    elif action == "lines":
        if len(parts) < 4:
            await callback.answer("Invalid action")
            return
        delta = int(parts[3])
        if thread:
            thread.line_limit = max(1, thread.line_limit + delta)
            thread.display_mode = "lines"  # Switch to lines mode
            line_limit = thread.line_limit
        else:
            project.line_limit = max(1, project.line_limit + delta)
            project.display_mode = "lines"  # Switch to lines mode
            line_limit = project.line_limit
        project_manager._save()
        await callback.answer(f"Lines: {line_limit}")

    # Update message
    global_defaults = get_global_defaults()
    display_mode = get_thread_setting(thread, "display_mode", global_defaults) if thread else global_defaults["display_mode"]
    line_limit = get_thread_setting(thread, "line_limit", global_defaults) if thread else global_defaults["line_limit"]

    text = _build_verbose_text(display_mode, line_limit)
    kb = verbose_menu_keyboard(display_mode, line_limit, short_id)

    await telegram_queue.edit(callback.message, text, reply_markup=kb)
