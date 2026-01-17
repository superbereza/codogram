"""Settings and info commands."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue

router = Router(name="settings")


@router.message(Command("get_debug_ids"))
async def cmd_get_debug_ids(message: Message, telegram_queue: TelegramQueue):
    """Show debug IDs - admin only (protected by middleware)."""
    thread_id = message.message_thread_id
    thread_info = f"\nThread ID: `{thread_id}`" if thread_id else "\nThread ID: None (General)"
    await telegram_queue.reply(
        message,
        f"Your user ID: `{message.from_user.id}`\n"
        f"This chat ID: `{message.chat.id}`{thread_info}"
    )


@router.message(Command("help"))
async def cmd_help(message: Message, telegram_queue: TelegramQueue):
    """Show available commands."""
    text = """*Everyday:*
/esc — Cancel current operation
/auto\\_accept — Toggle auto\\-accept mode

*Create:*
/thread — New topic in project directory
/branch — New feature branch \\+ topic ⁽¹⁾

*Complete:*
/clear — Clear context, start fresh
/finish — Merge branch, archive topic ⁽¹⁾

*Settings:*
/start — Connect Claude or show status
/settings — View current settings
/shift\\_tab — Cycle Claude approval mode
/restart — Force restart Claude
/get\\_debug\\_ids — Show chat and thread IDs

*Help:*
/help — This message

⁽¹⁾ _Only in chats with Topics enabled_"""

    await telegram_queue.reply(message, text)


def _build_settings_text(project, thread, tmux_name: str) -> str:
    """Build settings message text. Used by cmd_settings and callback handler."""
    from ..tmux import TmuxSession
    from ..services.session_state import SessionStateService

    # Get settings from context
    if thread:
        auto_accept = thread.auto_accept
        verbose = thread.verbose
        context_name = thread.name
        cwd = thread.worktree_path or project.cwd
    else:
        auto_accept = project.auto_accept
        verbose = project.verbose
        context_name = project.project_name
        cwd = project.cwd

    # Format toggle indicators
    auto_status = "● on" if auto_accept else "○ off"
    verbose_status = "● on" if verbose else "○ off"

    lines = [f"**{context_name}**", ""]
    lines.append("chat")
    lines.append(f"• auto-accept: {auto_status}")
    lines.append(f"• verbose: {verbose_status}")
    lines.append("")
    lines.append("claude")

    # Get Claude session state from tmux
    if tmux_name:
        tmux = TmuxSession(tmux_name, cwd)
        service = SessionStateService()
        result = service.get_status(tmux)

        if not result.success:
            lines.append(f"• mode: {result.error}")
            lines.append("• background tasks: ?")
            lines.append("• context: ?")
        else:
            sb = result.status_bar

            # Approval mode
            if sb.approval_mode == "accept edits":
                mode_text = "accept edits"
            elif sb.approval_mode == "plan mode":
                mode_text = "plan mode"
            else:
                mode_text = "default"
            lines.append(f"• mode: {mode_text}")
            lines.append(f"• background tasks: {sb.background_tasks}")

            if sb.context_percent is not None:
                lines.append(f"• context: {sb.context_percent}%")
            else:
                lines.append("• context: not displayed")
    else:
        lines.append("• mode: not connected")
        lines.append("• background tasks: ?")
        lines.append("• context: ?")

    return "\n".join(lines)


@router.message(Command("settings"))
async def cmd_settings(message: Message, telegram_queue: TelegramQueue):
    """Show current settings including Claude session state."""
    from ..keyboards import settings_keyboard

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    # Get tmux name for keyboard
    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
    else:
        tmux_name = f"claude-{project.project_name}"

    text = _build_settings_text(project, thread, tmux_name)
    kb = settings_keyboard(tmux_name)
    await telegram_queue.reply(message, text, reply_markup=kb)


@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message, telegram_queue: TelegramQueue):
    """Toggle auto-accept or reset all."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        # thread_id is None for General, or int for topics
        # In-memory key is None (not "null" string)
        thread = project.threads.get(thread_id)

    args = (message.text or "").split()[1:]

    # /auto_accept reset all - reset all to off
    if len(args) >= 2 and args[0].lower() == "reset" and args[1].lower() == "all":
        project.auto_accept = False
        if project.threads:
            for t in project.threads.values():
                t.auto_accept = False
        project_manager._save()
        await telegram_queue.reply(message, "Auto-accept reset to **OFF** for project and all threads.")
        return

    # /auto_accept - toggle current context
    if thread:
        thread.auto_accept = not thread.auto_accept
        status = "⚡ ON" if thread.auto_accept else "OFF"
        await telegram_queue.reply(message, f"Auto-accept for `{thread.name}`: **{status}**")
    else:
        project.auto_accept = not project.auto_accept
        status = "⚡ ON" if project.auto_accept else "OFF"
        await telegram_queue.reply(message, f"Auto-accept: **{status}**")
    project_manager._save()
