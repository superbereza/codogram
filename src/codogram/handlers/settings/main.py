# TODO: modularize - split into commands.py, display.py, callbacks.py
"""Settings and info commands."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from ..common import CommandStrict
from ...core.session_manager import project_manager
from ...telegram.queue import TelegramQueue
from ... import strings
from ...logging_config import logger
from ...telegram.sticker import StickerAdapter
from ...services.emoji_pack import EmojiPackService
from ...services.response_mode import ResponseModeService
from ...telegram.keyboards import avatar_pack_create_keyboard, avatar_pack_disable_keyboard

router = Router(name="settings_main")


def _cycle_response_mode(project, thread) -> tuple[str, str]:
    """Cycle response mode and return (new_mode, explanation).

    Returns:
        Tuple of (mode_name, explanation_string)
    """
    from ...core.session_manager import get_thread_setting
    from ...config import get_global_defaults

    modes = list(ResponseModeService.VALID_MODES)
    explanations = {
        "all": strings.RESPONSE_MODE_ALL,
        "polite": strings.RESPONSE_MODE_POLITE,
        "mentions": strings.RESPONSE_MODE_MENTIONS,
    }

    global_defaults = get_global_defaults()

    if thread:
        current = get_thread_setting(thread, "response_mode", global_defaults)
        try:
            next_idx = (modes.index(current) + 1) % len(modes)
        except ValueError:
            next_idx = 0
        thread.response_mode = modes[next_idx]
        new_mode = thread.response_mode
    else:
        # No thread - just use first mode
        new_mode = modes[0]

    return new_mode, explanations.get(new_mode, "")


@router.message(Command("get_debug_ids", ignore_case=True), CommandStrict())
async def cmd_get_debug_ids(message: Message, telegram_queue: TelegramQueue):
    """Show debug IDs - admin only (protected by middleware)."""
    thread_id = message.message_thread_id
    thread_info = f"\nThread ID: `{thread_id}`" if thread_id else "\nThread ID: None (General)"
    await telegram_queue.reply(
        message,
        f"Your user ID: `{message.from_user.id}`\n"
        f"This chat ID: `{message.chat.id}`{thread_info}"
    )


@router.message(Command("help", ignore_case=True), CommandStrict())
async def cmd_help(message: Message, telegram_queue: TelegramQueue):
    """Show help with Close button."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Close", callback_data="help_close")]
    ])
    await telegram_queue.reply(message, strings.HELP_TEXT, reply_markup=keyboard)


@router.callback_query(F.data == "help_close")
async def on_help_close(callback: CallbackQuery):
    """Close help message."""
    await callback.message.delete()
    await callback.answer()


def _build_settings_text(project, thread, tmux_name: str) -> str:
    """Build settings message text. Used by cmd_settings and callback handler."""
    from ...tmux.session import TmuxSession
    from ...services.session_state import SessionStateService
    from ...core.session_manager import get_thread_setting, get_project_setting
    from ...config import get_global_defaults

    global_defaults = get_global_defaults()

    # feat_avatar_pack is per-project (not per-thread)
    feat_avatar_pack = get_project_setting(project, "feat_avatar_pack", global_defaults)

    # Get settings from thread with fallback to global defaults
    if thread:
        auto_accept = get_thread_setting(thread, "auto_accept", global_defaults)
        display_mode = get_thread_setting(thread, "display_mode", global_defaults)
        line_limit = get_thread_setting(thread, "line_limit", global_defaults)
        display_bullet = get_thread_setting(thread, "display_bullet", global_defaults)
        display_thinking_text = get_thread_setting(thread, "display_thinking_text", global_defaults)
        working_status = get_thread_setting(thread, "working_status", global_defaults)
        response_mode = get_thread_setting(thread, "response_mode", global_defaults)
        feat_suggestions = get_thread_setting(thread, "feat_suggestions", global_defaults)
        context_name = thread.name
        cwd = thread.worktree_path or project.cwd
    else:
        # Fallback to global defaults when no thread
        auto_accept = global_defaults["auto_accept"]
        display_mode = global_defaults["display_mode"]
        line_limit = global_defaults["line_limit"]
        display_bullet = global_defaults["display_bullet"]
        display_thinking_text = global_defaults["display_thinking_text"]
        working_status = global_defaults["working_status"]
        response_mode = global_defaults["response_mode"]
        feat_suggestions = global_defaults["feat_suggestions"]
        context_name = project.project_name
        cwd = project.cwd

    # Format toggle indicators
    auto_status = "● on" if auto_accept else "○ off"
    bullet_status = "● on" if display_bullet else "○ off"
    thinking_status = "● on" if display_thinking_text else "○ off"
    working_status_text = "● on" if working_status else "○ off"

    # Format display_mode (verbose_mode)
    if display_mode == "lines":
        verbose_status = f"lines ({line_limit})"
    else:
        verbose_status = display_mode

    # Experimental features
    suggestions_status = "● on" if feat_suggestions else "○ off"
    avatar_pack_status = "● on" if feat_avatar_pack else "○ off"

    lines = [f"**{context_name}**", ""]
    lines.append("chat")
    lines.append(f"• /auto\\_accept: {auto_status}")
    lines.append(f"• /response\\_mode: {response_mode}")
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
    lines.append("ui")
    lines.append(f"• /verbose\\_mode: {verbose_status}")
    lines.append(f"• /display\\_bullet: {bullet_status}")
    lines.append(f"• /display\\_thinking\\_text: {thinking_status}")

    lines.append("")
    lines.append("experimental features")
    lines.append(f"• /working\\_status: {working_status_text}")
    lines.append(f"• /exp\\_suggestions: {suggestions_status}")
    lines.append(f"• /exp\\_avatar\\_pack: {avatar_pack_status}")
    lines.append("")
    lines.append(strings.SETTINGS_RESET_HINT)

    return "\n".join(lines)


@router.message(Command("settings", ignore_case=True), CommandStrict())
async def cmd_settings(message: Message, telegram_queue: TelegramQueue):
    """Show current settings including Claude session state."""
    from ...telegram.keyboards import settings_keyboard

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
    kb = settings_keyboard(tmux_name, page=0)
    await telegram_queue.reply(message, text, reply_markup=kb)


@router.message(Command("auto_accept", ignore_case=True), CommandStrict())
async def cmd_auto_accept(message: Message, telegram_queue: TelegramQueue):
    """Toggle auto-accept or reset all."""
    from ...core.session_manager import get_thread_setting
    from ...config import get_global_defaults

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
        if project.threads:
            for t in project.threads.values():
                t.auto_accept = False
        project_manager._save()
        await telegram_queue.reply(message, "Auto-accept reset to ○ off for all threads.")
        return

    # /auto_accept - toggle current context
    if thread:
        global_defaults = get_global_defaults()
        current = get_thread_setting(thread, "auto_accept", global_defaults)
        thread.auto_accept = not current
        status = "● on" if thread.auto_accept else "○ off"
        await telegram_queue.reply(message, f"Auto-accept: {status}")
        project_manager._save()
    else:
        await telegram_queue.reply(message, "Thread not found. Use /start first.")


@router.message(Command("verbose", ignore_case=True), CommandStrict())
async def cmd_verbose(message: Message, telegram_queue: TelegramQueue):
    """Alias for /verbose_mode (deprecated)."""
    from .verbose_menu import cmd_verbose_mode
    await cmd_verbose_mode(message, telegram_queue)


@router.message(Command("display_bullet", ignore_case=True), CommandStrict())
async def cmd_display_bullet(message: Message, telegram_queue: TelegramQueue):
    """Toggle bullet point prefix in tool messages."""
    from ...core.session_manager import get_thread_setting
    from ...config import get_global_defaults

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
        global_defaults = get_global_defaults()
        current = get_thread_setting(thread, "display_bullet", global_defaults)
        thread.display_bullet = not current
        status = "● on" if thread.display_bullet else "○ off"
        project_manager._save()
        await telegram_queue.reply(message, f"Bullet prefix: {status}")
    else:
        await telegram_queue.reply(message, "Thread not found. Use /start first.")


@router.message(Command("response_mode", ignore_case=True), CommandStrict())
async def cmd_response_mode(message: Message, telegram_queue: TelegramQueue):
    """Cycle response mode: all -> polite -> mentions -> all."""
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
        new_mode, explanation = _cycle_response_mode(project, thread)
        project_manager._save()
        await telegram_queue.reply(message, f"response mode: {new_mode}\n_{explanation}_")
    else:
        await telegram_queue.reply(message, "Thread not found. Use /start first.")


@router.message(Command("display_thinking_text", ignore_case=True), CommandStrict())
async def cmd_display_thinking_text(message: Message, telegram_queue: TelegramQueue):
    """Toggle display of <thinking> blocks in Claude's responses."""
    from ...core.session_manager import get_thread_setting
    from ...config import get_global_defaults

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
        global_defaults = get_global_defaults()
        current = get_thread_setting(thread, "display_thinking_text", global_defaults)
        thread.display_thinking_text = not current
        status = "● on" if thread.display_thinking_text else "○ off"
        project_manager._save()
        await telegram_queue.reply(message, f"Show thinking blocks: {status}")
    else:
        await telegram_queue.reply(message, "Thread not found. Use /start first.")


@router.message(Command("working_status", ignore_case=True), CommandStrict())
async def cmd_working_status(message: Message, telegram_queue: TelegramQueue):
    """Toggle working status indicator (Claude's activity)."""
    from ...core.session_manager import get_thread_setting
    from ...config import get_global_defaults

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
        global_defaults = get_global_defaults()
        current = get_thread_setting(thread, "working_status", global_defaults)
        thread.working_status = not current
        status = "● on" if thread.working_status else "○ off"
        project_manager._save()
        await telegram_queue.reply(message, f"Working status indicator: {status}")
    else:
        await telegram_queue.reply(message, "Thread not found. Use /start first.")


# Keep old command as alias for backward compat
@router.message(Command("exp_thinking_status", ignore_case=True), CommandStrict())
async def cmd_exp_thinking_status_alias(message: Message, telegram_queue: TelegramQueue):
    """Alias for /working_status (deprecated)."""
    await cmd_working_status(message, telegram_queue)


@router.message(Command("exp_suggestions", ignore_case=True), CommandStrict())
async def cmd_exp_suggestions(message: Message, telegram_queue: TelegramQueue):
    """Toggle suggestions feature."""
    from ...core.session_manager import get_thread_setting
    from ...config import get_global_defaults

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
        global_defaults = get_global_defaults()
        current = get_thread_setting(thread, "feat_suggestions", global_defaults)
        thread.feat_suggestions = not current
        status = "● on" if thread.feat_suggestions else "○ off"
        project_manager._save()
        await telegram_queue.reply(message, f"Suggestions: {status}")
    else:
        await telegram_queue.reply(message, "Thread not found. Use /start first.")


@router.message(Command("exp_avatar_pack", ignore_case=True), CommandStrict())
async def cmd_exp_avatar_pack(message: Message, telegram_queue: TelegramQueue):
    """Toggle avatar pack feature (per-project setting)."""
    from ...core.session_manager import get_project_setting
    from ...config import get_global_defaults

    chat_id = message.chat.id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, strings.PROJECT_NOT_REGISTERED)
        return

    global_defaults = get_global_defaults()
    current = get_project_setting(project, "feat_avatar_pack", global_defaults)

    if current:
        kb = avatar_pack_disable_keyboard()
        await telegram_queue.reply(message, strings.EMOJI_PACK_DISABLE_PROMPT, reply_markup=kb)
    else:
        kb = avatar_pack_create_keyboard()
        await telegram_queue.reply(message, strings.EMOJI_PACK_CREATE_PROMPT, reply_markup=kb)


@router.callback_query(F.data.startswith("avatar_pack:"))
async def callback_avatar_pack(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle avatar pack button presses."""
    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("Invalid callback")
        return
    action = parts[1]
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
        logger.info(f"Avatar pack creation started for chat {chat_id}")
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
        logger.info(f"Avatar pack deletion requested for chat {chat_id}")
        await telegram_queue.edit(callback.message, strings.EMOJI_PACK_DELETED)
        await callback.answer()
        await service.delete_pack(chat_id)


@router.callback_query(F.data == "settings:noop")
async def callback_settings_noop(callback: CallbackQuery):
    """Handle placeholder button press."""
    await callback.answer()


@router.callback_query(F.data.startswith("settings:") & F.data.contains(":page:"))
async def callback_settings_page(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle settings page navigation."""
    from ...telegram.keyboards import settings_keyboard
    from ...telegram.keyboards.settings import _short_id

    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Invalid callback")
        return

    short_id = parts[1]
    try:
        new_page = int(parts[3])
    except ValueError:
        await callback.answer("Invalid page")
        return

    # Find project and thread by short ID to get tmux_name
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

    if not project or not tmux_name:
        await callback.answer("Project not found")
        return

    # Rebuild keyboard with new page
    kb = settings_keyboard(tmux_name, page=new_page)

    # Edit message (text stays same, only keyboard changes)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("set:"))
async def callback_settings(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle settings keyboard button presses."""
    from ...telegram.keyboards.settings import _short_id
    from ...telegram.keyboards import settings_keyboard
    from ...core.session_manager import get_thread_setting, get_project_setting
    from ...config import get_global_defaults

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

    global_defaults = get_global_defaults()

    if action == "aa":
        if thread:
            current = get_thread_setting(thread, "auto_accept", global_defaults)
            thread.auto_accept = not current
            status = "● on" if thread.auto_accept else "○ off"
            project_manager._save()
            await callback.answer(f"Auto-accept: {status}")
        else:
            await callback.answer("Thread not found")
            return

    elif action == "v":
        # Open verbose mode menu
        from ...telegram.keyboards.verbose_menu import verbose_menu_keyboard
        from .verbose_menu import _build_verbose_text

        if thread:
            display_mode = get_thread_setting(thread, "display_mode", global_defaults)
            line_limit = get_thread_setting(thread, "line_limit", global_defaults)
        else:
            display_mode = global_defaults["display_mode"]
            line_limit = global_defaults["line_limit"]

        text = _build_verbose_text(display_mode, line_limit)
        kb = verbose_menu_keyboard(display_mode, line_limit, short_id)
        await telegram_queue.edit(callback.message, text, reply_markup=kb)
        await callback.answer()
        return  # Don't update settings message

    elif action == "m":
        from ...tmux.session import TmuxSession
        from ...services.session_state import SessionStateService

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

    elif action == "rm":  # response_mode
        if thread:
            new_mode, _ = _cycle_response_mode(project, thread)
            project_manager._save()
            await callback.answer(f"Response: {new_mode}")
        else:
            await callback.answer("Thread not found")
            return

    elif action == "db":  # display_bullet
        if thread:
            current = get_thread_setting(thread, "display_bullet", global_defaults)
            thread.display_bullet = not current
            status = "● on" if thread.display_bullet else "○ off"
            project_manager._save()
            await callback.answer(f"Bullet prefix: {status}")
        else:
            await callback.answer("Thread not found")
            return

    elif action == "dt":  # display_thinking_text
        if thread:
            current = get_thread_setting(thread, "display_thinking_text", global_defaults)
            thread.display_thinking_text = not current
            status = "● on" if thread.display_thinking_text else "○ off"
            project_manager._save()
            await callback.answer(f"Thinking text: {status}")
        else:
            await callback.answer("Thread not found")
            return

    elif action == "ws":  # working_status
        if thread:
            current = get_thread_setting(thread, "working_status", global_defaults)
            thread.working_status = not current
            status = "● on" if thread.working_status else "○ off"
            project_manager._save()
            await callback.answer(f"Working status: {status}")
        else:
            await callback.answer("Thread not found")
            return

    elif action == "es":  # exp_suggestions
        if thread:
            current = get_thread_setting(thread, "feat_suggestions", global_defaults)
            thread.feat_suggestions = not current
            status = "● on" if thread.feat_suggestions else "○ off"
            project_manager._save()
            await callback.answer(f"Suggestions: {status}")
        else:
            await callback.answer("Thread not found")
            return

    elif action == "ea":  # exp_avatar_pack (per-project setting)
        current = get_project_setting(project, "feat_avatar_pack", global_defaults)
        project.feat_avatar_pack = not current
        status = "● on" if project.feat_avatar_pack else "○ off"
        project_manager._save()
        await callback.answer(f"Avatar pack: {status}")

    # Determine current page from action code
    from ...telegram.keyboards.settings import SETTINGS_BUTTON_GROUPS, _COMMAND_TO_ACTION
    current_page = 0
    action_to_cmd = {v: k for k, v in _COMMAND_TO_ACTION.items()}
    if action in action_to_cmd:
        cmd = action_to_cmd[action]
        for i, group in enumerate(SETTINGS_BUTTON_GROUPS):
            if cmd in group:
                current_page = i
                break

    # Update the settings message using shared helper
    text = _build_settings_text(project, thread, tmux_name)
    kb = settings_keyboard(tmux_name, page=current_page)
    await telegram_queue.edit(callback.message, text, reply_markup=kb)


@router.message(Command("test_verbose_aa", ignore_case=True), CommandStrict())
async def cmd_test_verbose_aa(message: Message, telegram_queue: TelegramQueue):
    """TEST: Toggle verbose auto-accept (shows what's being auto-accepted)."""
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
        current = getattr(thread, 'test_verbose_auto_accept', False)
        thread.test_verbose_auto_accept = not current
        status = "● on" if thread.test_verbose_auto_accept else "○ off"
        await telegram_queue.reply(message, f"TEST verbose auto-accept: {status}")
    else:
        await telegram_queue.reply(message, "Thread not found.")
