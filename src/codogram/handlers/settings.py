"""Settings and info commands."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .. import strings
from ..adapters.sticker import StickerAdapter
from ..services.emoji_pack import EmojiPackService
from ..keyboards import avatar_pack_create_keyboard, avatar_pack_disable_keyboard

router = Router(name="settings")


@router.message(Command("get_debug_ids", ignore_case=True))
async def cmd_get_debug_ids(message: Message, telegram_queue: TelegramQueue):
    """Show debug IDs - admin only (protected by middleware)."""
    thread_id = message.message_thread_id
    thread_info = f"\nThread ID: `{thread_id}`" if thread_id else "\nThread ID: None (General)"
    await telegram_queue.reply(
        message,
        f"Your user ID: `{message.from_user.id}`\n"
        f"This chat ID: `{message.chat.id}`{thread_info}"
    )


@router.message(Command("help", ignore_case=True))
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

    # Format toggle indicators (strip backticks for inline display)
    auto_status = "● on" if auto_accept else "○ off"
    verbose_status = "● on" if verbose else "○ off"

    # Experimental features
    feat_thinking = thread.feat_thinking_status if thread else project.feat_thinking_status
    # Note: feat_suggestions is project-level only
    thinking_status = "● on" if feat_thinking else "○ off"
    suggestions_status = "● on" if project.feat_suggestions else "○ off"

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
                mode_text = "⏵⏵ accept edits"
            elif sb.approval_mode == "plan mode":
                mode_text = "⏸ plan mode"
            else:
                mode_text = "default"
            lines.append(f"• mode: {mode_text}")
            lines.append("  (use /shift_tab to cycle)")
            lines.append(f"• background tasks: {sb.background_tasks}")

            if sb.context_percent is not None:
                lines.append(f"• context: {sb.context_percent}%")
            else:
                lines.append("• context: not displayed")
    else:
        lines.append("• mode: not connected")
        lines.append("• background tasks: ?")
        lines.append("• context: ?")

    lines.append("")
    lines.append("experimental features")
    lines.append(f"• /exp\\_thinking\\_status: {thinking_status}")
    lines.append(f"• /exp\\_suggestions: {suggestions_status}")

    return "\n".join(lines)


@router.message(Command("settings", ignore_case=True))
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


@router.message(Command("auto_accept", ignore_case=True))
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
        await telegram_queue.reply(message, "Auto-accept reset to ○ off for project and all threads.")
        return

    # /auto_accept - toggle current context
    if thread:
        thread.auto_accept = not thread.auto_accept
        status = "● on" if thread.auto_accept else "○ off"
        await telegram_queue.reply(message, f"Auto-accept: {status}")
    else:
        project.auto_accept = not project.auto_accept
        status = "● on" if project.auto_accept else "○ off"
        await telegram_queue.reply(message, f"Auto-accept: {status}")
    project_manager._save()


@router.message(Command("verbose", ignore_case=True))
async def cmd_verbose(message: Message, telegram_queue: TelegramQueue):
    """Toggle verbose output mode."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    # Toggle verbose
    if thread:
        thread.verbose = not thread.verbose
        status = "● on" if thread.verbose else "○ off"
    else:
        project.verbose = not project.verbose
        status = "● on" if project.verbose else "○ off"

    project_manager._save()
    await telegram_queue.reply(message, f"Verbose output: {status}")


@router.message(Command("exp_thinking_status", ignore_case=True))
async def cmd_exp_thinking_status(message: Message, telegram_queue: TelegramQueue):
    """Toggle thinking status feature."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    if thread:
        thread.feat_thinking_status = not thread.feat_thinking_status
        status = "● on" if thread.feat_thinking_status else "○ off"
    else:
        project.feat_thinking_status = not project.feat_thinking_status
        status = "● on" if project.feat_thinking_status else "○ off"

    project_manager._save()
    await telegram_queue.reply(message, f"Thinking status: {status}")


@router.message(Command("exp_suggestions", ignore_case=True))
async def cmd_exp_suggestions(message: Message, telegram_queue: TelegramQueue):
    """Toggle suggestions feature (chat-wide)."""
    chat_id = message.chat.id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    project.feat_suggestions = not project.feat_suggestions
    status = "● on" if project.feat_suggestions else "○ off"

    project_manager._save()
    await telegram_queue.reply(message, f"Suggestions (all topics): {status}")


@router.message(Command("exp_avatar_pack", ignore_case=True))
async def cmd_exp_avatar_pack(message: Message, telegram_queue: TelegramQueue):
    """Toggle avatar pack feature."""
    chat_id = message.chat.id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, strings.PROJECT_NOT_REGISTERED)
        return

    if project.feat_avatar_pack:
        kb = avatar_pack_disable_keyboard()
        await telegram_queue.reply(message, strings.EMOJI_PACK_DISABLE_PROMPT, reply_markup=kb)
    else:
        kb = avatar_pack_create_keyboard()
        await telegram_queue.reply(message, strings.EMOJI_PACK_CREATE_PROMPT, reply_markup=kb)


@router.callback_query(F.data.startswith("avatar_pack:"))
async def callback_avatar_pack(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle avatar pack button presses."""
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    if action == "cancel":
        await telegram_queue.edit(callback.message, strings.CANCELLED)
        await callback.answer()
        return

    # Create service with adapter (layered architecture)
    adapter = StickerAdapter(callback.bot)
    service = EmojiPackService(adapter)

    if action == "create":
        await telegram_queue.edit(callback.message, strings.EMOJI_PACK_CREATING)
        await callback.answer()

        thread_id = callback.message.message_thread_id

        # Get participants (admins for now, members added on join)
        try:
            admins = await callback.bot.get_chat_administrators(chat_id)
            participants = [admin.user for admin in admins if not admin.user.is_bot]
        except Exception as e:
            await telegram_queue.send(
                chat_id, strings.EMOJI_PACK_ERROR.format(error=str(e)), thread_id=thread_id
            )
            return

        # Create pack
        pack_name = await service.create_pack(chat_id, participants)
        if pack_name:
            pack_link = f"t.me/addemoji/{pack_name}"
            await telegram_queue.send(
                chat_id,
                strings.EMOJI_PACK_CREATED.format(pack_link=pack_link),
                thread_id=thread_id,
            )
        else:
            await telegram_queue.send(
                chat_id, strings.EMOJI_PACK_ERROR.format(error="Unknown error"), thread_id=thread_id
            )

    elif action == "disable":
        await telegram_queue.edit(callback.message, strings.EMOJI_PACK_DELETED)
        await callback.answer()
        await service.delete_pack(chat_id)


@router.callback_query(F.data.startswith("set:"))
async def callback_settings(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle settings keyboard button presses."""
    from ..keyboards.settings import _short_id
    from ..keyboards import settings_keyboard

    data = callback.data
    parts = data.split(":")

    # Handle close action (no short_id needed)
    if len(parts) >= 2 and parts[1] == "close":
        await callback.message.delete()
        await callback.answer()
        return

    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    action = parts[1]  # aa (auto_accept), v (verbose), m (mode)
    short_id = parts[2]

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
        # Check project-level tmux
        p_tmux = f"claude-{p.project_name}"
        if _short_id(p_tmux) == short_id:
            project = p
            tmux_name = p_tmux
            break

    if not project:
        await callback.answer("Project not found")
        return

    if action == "aa":
        if thread:
            thread.auto_accept = not thread.auto_accept
            status = "● on" if thread.auto_accept else "○ off"
        else:
            project.auto_accept = not project.auto_accept
            status = "● on" if project.auto_accept else "○ off"
        project_manager._save()
        await callback.answer(f"Auto-accept: {status}")

    elif action == "v":
        if thread:
            thread.verbose = not thread.verbose
            status = "● on" if thread.verbose else "○ off"
        else:
            project.verbose = not project.verbose
            status = "● on" if project.verbose else "○ off"
        project_manager._save()
        await callback.answer(f"Verbose: {status}")

    elif action == "m":
        from ..tmux import TmuxSession
        from ..services.session_state import SessionStateService

        # Get cwd for tmux
        if thread:
            cwd = thread.worktree_path or project.cwd
        else:
            cwd = project.cwd

        tmux = TmuxSession(tmux_name, cwd)
        service = SessionStateService()
        result = service.cycle_approval_mode(tmux)

        if not result.success:
            await callback.answer(result.error)
            # Still update the message to refresh state
        else:
            # Format mode for answer
            if result.new_mode == "accept edits":
                mode_text = "⏵⏵ accept edits"
            elif result.new_mode == "plan mode":
                mode_text = "⏸ plan mode"
            else:
                mode_text = "default"
            await callback.answer(f"Mode: {mode_text}")

    # Update the settings message using shared helper
    text = _build_settings_text(project, thread, tmux_name)
    kb = settings_keyboard(tmux_name)
    await telegram_queue.edit(callback.message, text, reply_markup=kb)
