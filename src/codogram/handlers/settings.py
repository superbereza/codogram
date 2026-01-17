"""Settings and info commands."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .. import strings

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


@router.message(Command("settings"))
async def cmd_settings(message: Message, telegram_queue: TelegramQueue):
    """Show current settings including Claude session state."""
    from ..tmux import TmuxSession
    from ..services.session_state import SessionStateService

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    # Get auto-accept status
    if thread:
        auto_status = strings.STATUS_ON if thread.auto_accept else strings.STATUS_OFF
        context_name = thread.name
        tmux_name = thread.get_tmux_session(project.project_name)
        cwd = thread.worktree_path or project.cwd
    else:
        auto_status = strings.STATUS_ON if project.auto_accept else strings.STATUS_OFF
        context_name = project.project_name
        tmux_name = project.tmux_session
        cwd = project.cwd

    lines = [f"session state (`{context_name}`)"]
    lines.append(f"• auto-accept: {auto_status}")

    # Get Claude session state from tmux
    if tmux_name:
        tmux = TmuxSession(tmux_name, cwd)
        service = SessionStateService()
        result = service.get_status(tmux)

        if not result.success:
            lines.append(f"• claude: {result.error}")
        else:
            sb = result.status_bar

            # Approval mode (None = default mode)
            if sb.approval_mode == "accept edits":
                mode_text = "⏵⏵ accept edits on"
            elif sb.approval_mode == "plan mode":
                mode_text = "⏸ plan mode on"
            else:
                mode_text = "default mode on"
            lines.append(f"• mode: {mode_text}, (/shift\\_tab to cycle)")

            # Background tasks
            if sb.background_tasks == 0:
                lines.append("• no background tasks")
            elif sb.background_tasks == 1:
                lines.append("• 1 background task")
            else:
                lines.append(f"• {sb.background_tasks} background tasks")

            # Context
            if sb.context_percent is not None:
                lines.append(f"• context left until autocompact: {sb.context_percent}%")
            else:
                lines.append("• context left until autocompact: not displayed")
    else:
        lines.append("• claude: not connected")

    # Experimental features
    if thread:
        thinking_status = strings.STATUS_ON if thread.feat_thinking_status else strings.STATUS_OFF
        suggestions_status = strings.STATUS_ON if thread.feat_suggestions else strings.STATUS_OFF
    else:
        thinking_status = strings.STATUS_ON if project.feat_thinking_status else strings.STATUS_OFF
        suggestions_status = strings.STATUS_ON if project.feat_suggestions else strings.STATUS_OFF

    lines.append("")
    lines.append("experimental:")
    lines.append(f"• thinking-status: {thinking_status}")
    lines.append(f"• suggestions: {suggestions_status}")

    await telegram_queue.reply(message, "\n".join(lines))


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
        await telegram_queue.reply(message, f"Auto-accept reset to **{strings.STATUS_OFF}** for project and all threads.")
        return

    # /auto_accept - toggle current context
    if thread:
        thread.auto_accept = not thread.auto_accept
        status = strings.STATUS_ON if thread.auto_accept else strings.STATUS_OFF
        await telegram_queue.reply(message, f"Auto-accept for `{thread.name}`: **{status}**")
    else:
        project.auto_accept = not project.auto_accept
        status = strings.STATUS_ON if project.auto_accept else strings.STATUS_OFF
        await telegram_queue.reply(message, f"Auto-accept: **{status}**")
    project_manager._save()


@router.message(Command("feat_toggle_thinking_status"))
async def cmd_feat_toggle_thinking_status(message: Message, telegram_queue: TelegramQueue):
    """Toggle thinking status display (experimental)."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = project.threads.get(thread_id) if project.threads else None

    if thread:
        thread.feat_thinking_status = not thread.feat_thinking_status
        status = strings.STATUS_ON if thread.feat_thinking_status else strings.STATUS_OFF
        await telegram_queue.reply(message, f"thinking-status: **{status}**")
    else:
        project.feat_thinking_status = not project.feat_thinking_status
        status = strings.STATUS_ON if project.feat_thinking_status else strings.STATUS_OFF
        await telegram_queue.reply(message, f"thinking-status: **{status}**")
    project_manager._save()


@router.message(Command("feat_toggle_suggestions"))
async def cmd_feat_toggle_suggestions(message: Message, telegram_queue: TelegramQueue):
    """Toggle input suggestions display (experimental)."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = project.threads.get(thread_id) if project.threads else None

    if thread:
        thread.feat_suggestions = not thread.feat_suggestions
        status = strings.STATUS_ON if thread.feat_suggestions else strings.STATUS_OFF
        await telegram_queue.reply(message, f"suggestions: **{status}**")
    else:
        project.feat_suggestions = not project.feat_suggestions
        status = strings.STATUS_ON if project.feat_suggestions else strings.STATUS_OFF
        await telegram_queue.reply(message, f"suggestions: **{status}**")
    project_manager._save()
