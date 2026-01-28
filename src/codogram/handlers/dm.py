"""DM-specific handlers for onboarding and dashboard."""
import asyncio
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_NOT_MEMBER, ADMINISTRATOR, MEMBER
from aiogram.enums import ChatType

from .. import strings
from ..config import get_user_onboarded, set_user_onboarded, settings, get_global_defaults
from ..telegram.keyboards.dm_onboarding import (
    carousel_keyboard,
    validation_recheck_keyboard,
    dashboard_keyboard,
    cta_keyboard,
    privacy_hint_keyboard,
)
from ..services.dm_onboarding import (
    get_slide_content,
    get_total_slides,
    run_critical_checks,
    run_warning_checks,
)
from ..services.dashboard import format_dashboard, ProjectInfo
from ..core.session_manager import project_manager
from ..tmux.launcher import is_tmux_session_exists
from ..telegram.queue import TelegramQueue

router = Router(name="dm")


# ===== Filters =====

def is_dm(message: Message) -> bool:
    """Check if message is from DM (private chat)."""
    return message.chat.type == ChatType.PRIVATE


def is_admin(message: Message) -> bool:
    """Check if user is admin."""
    return message.from_user.id in settings.get_admin_ids()


# ===== /start in DM =====

@router.message(Command("start"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_start(message: Message, telegram_queue: TelegramQueue):
    """Handle /start in DM."""
    if not is_admin(message):
        return  # Silently ignore non-admins in DM

    await handle_dm_start(message, telegram_queue)


async def handle_dm_start(message: Message, telegram_queue: TelegramQueue):
    """Main logic for /start in DM."""
    user_id = message.from_user.id

    if get_user_onboarded(user_id):
        await show_mini_status(message, telegram_queue)
    else:
        await run_onboarding(message, telegram_queue)


async def show_mini_status(message: Message, telegram_queue: TelegramQueue):
    """Show mini status for returning users."""
    # Count projects and active tmux sessions
    projects = project_manager.projects
    project_count = len(projects)

    session_count = 0
    for p in projects.values():
        for t in p.threads.values():
            tmux_name = t.get_tmux_session(p.project_name)
            if is_tmux_session_exists(tmux_name):
                session_count += 1

    text = strings.DM_MINI_STATUS.format(
        projects=project_count,
        sessions=session_count,
    )
    await telegram_queue.send(message.chat.id, text)


async def run_onboarding(message: Message, telegram_queue: TelegramQueue):
    """Run full onboarding flow."""
    # 1. Welcome message
    await telegram_queue.send(message.chat.id, strings.DM_WELCOME)

    # Small delay before carousel
    await asyncio.sleep(0.3)

    # 2. First slide of carousel
    slide_content = get_slide_content(0)
    keyboard = carousel_keyboard(0, get_total_slides())
    await telegram_queue.send(
        message.chat.id,
        slide_content,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# ===== Carousel callbacks =====

@router.callback_query(F.data.startswith("onb:slide:"))
async def on_carousel_slide(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle carousel navigation."""
    if not callback.message:
        await callback.answer()
        return

    # Parse slide number from callback data
    try:
        slide_num = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer("Invalid slide")
        return

    total = get_total_slides()

    # Check if this is the last slide -> show validation
    if slide_num >= total:
        await show_validation(callback, telegram_queue)
        await callback.answer()
        return

    # Show slide
    content = get_slide_content(slide_num)
    if content is None:
        await callback.answer("Invalid slide")
        return

    keyboard = carousel_keyboard(slide_num, total)
    await telegram_queue.edit(
        callback.message,
        content,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await callback.answer()


async def show_validation(callback: CallbackQuery, telegram_queue: TelegramQueue, edit_existing: bool = False):
    """Show validation results.

    Args:
        edit_existing: If True, edit callback.message. If False, send new messages (keeps carousel).
    """
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    bot = callback.bot

    # Run validation
    success = await run_validation_check(
        chat_id=chat_id,
        telegram_queue=telegram_queue,
        bot=bot,
    )

    # Mark user as onboarded if validation passed
    if success:
        set_user_onboarded(user_id)


async def run_validation_check(
    chat_id: int,
    telegram_queue: TelegramQueue,
    bot: Bot,
) -> bool:
    """Run validation checks synchronously.

    Returns True if all critical checks passed.
    """
    # Run all critical checks
    critical_results = run_critical_checks()
    critical_errors = [r for r in critical_results if not r.ok]

    # Build result text
    lines = []

    if critical_errors:
        lines.append("`[x]` Issues found")
    else:
        lines.append("`[v]` Environment ready")

    lines.append("")
    lines.append("Critical:")

    for r in critical_results:
        icon = "`[v]`" if r.ok else "`[x]`"
        lines.append(f"{icon} {r.name}")

    # If critical errors, show error with hints and recheck button
    if critical_errors:
        lines.append("")
        for r in critical_errors:
            lines.append(f"`[x]` {r.message}")
            if r.fix_hint:
                lines.append(f"`{r.fix_hint}`")

        lines.append("")
        lines.append("Fix issues and recheck.")

        text = "\n".join(lines)
        keyboard = validation_recheck_keyboard()
        await telegram_queue.send(chat_id, text, reply_markup=keyboard)
        return False

    # Run optional checks
    optional_results = run_warning_checks()

    lines.append("")
    lines.append("Optional:")

    for r in optional_results:
        icon = "`[v]`" if r.ok else "`[-]`"
        lines.append(f"{icon} {r.name}")

    text = "\n".join(lines)
    await telegram_queue.send(chat_id, text)

    # Delay before manual check hint
    await asyncio.sleep(0.5)

    # Send privacy mode hint with "Done" button
    keyboard = privacy_hint_keyboard()
    await telegram_queue.send(chat_id, strings.DM_MANUAL_CHECK, reply_markup=keyboard)

    # CTA will be sent after user clicks "Done"
    return True


@router.callback_query(F.data == "onb:recheck")
async def on_recheck(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle recheck validation button."""
    if not callback.message:
        await callback.answer()
        return

    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    bot = callback.bot

    # Delete the error message with the button
    try:
        await bot.delete_message(chat_id, callback.message.message_id)
    except Exception:
        pass

    # Run validation
    success = await run_validation_check(
        chat_id=chat_id,
        telegram_queue=telegram_queue,
        bot=bot,
    )

    if success:
        set_user_onboarded(user_id)

    await callback.answer()


@router.callback_query(F.data == "onb:privacy_done")
async def on_privacy_done(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle 'Done' button on privacy mode hint."""
    if not callback.message:
        await callback.answer()
        return

    chat_id = callback.message.chat.id
    bot = callback.bot

    # Remove keyboard from the hint message
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Send CTA
    bot_info = await bot.get_me()
    cta_text = strings.DM_CTA
    keyboard = cta_keyboard(bot_info.username)
    await telegram_queue.send(chat_id, cta_text, reply_markup=keyboard)

    await callback.answer()


# ===== /intro =====

@router.message(Command("intro"), F.chat.type == ChatType.PRIVATE)
async def cmd_intro(message: Message, telegram_queue: TelegramQueue):
    """Show onboarding again."""
    if not is_admin(message):
        return

    await run_onboarding(message, telegram_queue)


# ===== /check_env =====

@router.message(Command("check_env"), F.chat.type == ChatType.PRIVATE)
async def cmd_check_env(message: Message, telegram_queue: TelegramQueue, bot: Bot):
    """Run environment validation check."""
    if not is_admin(message):
        return

    await run_validation_check(
        chat_id=message.chat.id,
        telegram_queue=telegram_queue,
        bot=bot,
    )


# ===== /dashboard =====

@router.message(Command("dashboard"), F.chat.type == ChatType.PRIVATE)
async def cmd_dashboard(message: Message, telegram_queue: TelegramQueue, bot: Bot):
    """Show dashboard with all projects."""
    if not is_admin(message):
        return

    await show_dashboard(message.chat.id, telegram_queue, bot)


async def gather_project_info(bot: Bot) -> list[ProjectInfo]:
    """Gather info about all projects for dashboard."""
    projects_list = []
    for project in project_manager.projects.values():
        if not project.chat_id:
            continue

        try:
            chat = await bot.get_chat(project.chat_id)
            member_count = await bot.get_chat_member_count(project.chat_id)
            member_count = max(0, member_count - 1)

            active = 0
            for t in project.threads.values():
                tmux_name = t.get_tmux_session(project.project_name)
                if is_tmux_session_exists(tmux_name):
                    active += 1

            creator = "unknown"
            try:
                admins = await bot.get_chat_administrators(project.chat_id)
                for admin in admins:
                    if admin.status == "creator":
                        creator = admin.user.username or str(admin.user.id)
                        break
            except Exception:
                pass

            projects_list.append(ProjectInfo(
                chat_name=chat.title or "Untitled",
                directory=project.cwd or "unknown",
                creator=creator,
                members=member_count,
                active_sessions=active,
            ))
        except Exception:
            continue

    return projects_list


async def show_dashboard(chat_id: int, telegram_queue: TelegramQueue, bot: Bot):
    """Render and send dashboard."""
    projects_list = await gather_project_info(bot)
    text = format_dashboard(projects_list)
    keyboard = dashboard_keyboard()
    await telegram_queue.send(chat_id, text, reply_markup=keyboard)


@router.callback_query(F.data == "dash:refresh")
async def on_dash_refresh(callback: CallbackQuery, telegram_queue: TelegramQueue, bot: Bot):
    """Handle dashboard refresh - edit existing message instead of sending new."""
    if not callback.message:
        await callback.answer()
        return

    projects_list = await gather_project_info(bot)
    text = format_dashboard(projects_list)
    keyboard = dashboard_keyboard()
    await telegram_queue.edit(callback.message, text, reply_markup=keyboard)
    await callback.answer("Refreshed")


@router.callback_query(F.data == "dash:close")
async def on_dash_close(callback: CallbackQuery):
    """Handle dashboard close - delete message."""
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
    await callback.answer()


# ===== Bot added to chat =====

@router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> (ADMINISTRATOR | MEMBER))
)
async def on_bot_added_to_chat(event: ChatMemberUpdated, bot: Bot):
    """Handle bot being added to a chat."""
    # Skip DM
    if event.chat.type == ChatType.PRIVATE:
        return

    chat_name = event.chat.title or "Untitled"
    creator = event.from_user.username or str(event.from_user.id)

    # Try to get invite link
    link = None
    try:
        link = event.chat.invite_link
    except Exception:
        pass

    # Format message
    if link:
        text = strings.DM_BOT_ADDED_WITH_LINK.format(
            chat_name=chat_name,
            link=link,
            creator=creator,
        )
    else:
        text = strings.DM_BOT_ADDED.format(
            chat_name=chat_name,
            creator=creator,
        )

    # Send to all admins
    for admin_id in settings.get_admin_ids():
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            # Admin might have blocked bot or never started DM
            pass


# ===== /settings in DM =====

def _build_dm_settings_text() -> str:
    """Build settings message text for DM (global defaults)."""
    defaults = get_global_defaults()

    auto_status = "● on" if defaults["auto_accept"] else "○ off"
    response_mode = defaults["response_mode"]

    if defaults["display_mode"] == "lines":
        verbose_status = f"lines ({defaults['line_limit']})"
    else:
        verbose_status = defaults["display_mode"]

    bullet_status = "● on" if defaults["display_bullet"] else "○ off"
    thinking_status = "● on" if defaults["display_thinking_text"] else "○ off"
    working_stat = "● on" if defaults["working_status"] else "○ off"
    suggestions_status = "● on" if defaults["feat_suggestions"] else "○ off"
    avatar_pack_status = "● on" if defaults["feat_avatar_pack"] else "○ off"

    lines = [strings.DM_SETTINGS_HEADER, ""]
    lines.append("chat")
    lines.append(f"• /auto\\_accept: {auto_status}")
    lines.append(f"• /response\\_mode: {response_mode}")
    lines.append("")
    lines.append("ui")
    lines.append(f"• /verbose\\_mode: {verbose_status}")
    lines.append(f"• /display\\_bullet: {bullet_status}")
    lines.append(f"• /display\\_thinking\\_text: {thinking_status}")
    lines.append("")
    lines.append("experimental features")
    lines.append(f"• /working\\_status: {working_stat}")
    lines.append(f"• /exp\\_suggestions: {suggestions_status}")
    lines.append(f"• /exp\\_avatar\\_pack: {avatar_pack_status}")
    lines.append("")
    lines.append(strings.DM_SETTINGS_HINT)

    return "\n".join(lines)


@router.message(Command("settings"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_settings(message: Message, telegram_queue: TelegramQueue):
    """Show global settings in DM."""
    if not is_admin(message):
        return

    from ..telegram.keyboards.settings import settings_keyboard_dm

    text = _build_dm_settings_text()
    kb = settings_keyboard_dm(page=0)
    await telegram_queue.send(message.chat.id, text, reply_markup=kb)


# ===== DM settings commands (change global defaults) =====

@router.message(Command("auto_accept"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_auto_accept(message: Message, telegram_queue: TelegramQueue):
    """Toggle auto_accept global default."""
    if not is_admin(message):
        return
    from ..config import set_global_default
    defaults = get_global_defaults()
    new_value = not defaults["auto_accept"]
    set_global_default("auto_accept", new_value)
    status = "● on" if new_value else "○ off"
    await telegram_queue.send(message.chat.id, f"Global auto-accept: {status}")


@router.message(Command("response_mode"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_response_mode(message: Message, telegram_queue: TelegramQueue):
    """Cycle response_mode global default."""
    if not is_admin(message):
        return
    from ..config import set_global_default
    defaults = get_global_defaults()
    modes = ["all", "polite", "mentions"]
    current = defaults["response_mode"]
    try:
        next_idx = (modes.index(current) + 1) % len(modes)
    except ValueError:
        next_idx = 0
    new_mode = modes[next_idx]
    set_global_default("response_mode", new_mode)
    await telegram_queue.send(message.chat.id, f"Global response mode: {new_mode}")


@router.message(Command("display_bullet"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_display_bullet(message: Message, telegram_queue: TelegramQueue):
    """Toggle display_bullet global default."""
    if not is_admin(message):
        return
    from ..config import set_global_default
    defaults = get_global_defaults()
    new_value = not defaults["display_bullet"]
    set_global_default("display_bullet", new_value)
    status = "● on" if new_value else "○ off"
    await telegram_queue.send(message.chat.id, f"Global bullet prefix: {status}")


@router.message(Command("display_thinking_text"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_display_thinking(message: Message, telegram_queue: TelegramQueue):
    """Toggle display_thinking_text global default."""
    if not is_admin(message):
        return
    from ..config import set_global_default
    defaults = get_global_defaults()
    new_value = not defaults["display_thinking_text"]
    set_global_default("display_thinking_text", new_value)
    status = "● on" if new_value else "○ off"
    await telegram_queue.send(message.chat.id, f"Global thinking text: {status}")


@router.message(Command("working_status"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_working_status(message: Message, telegram_queue: TelegramQueue):
    """Toggle working_status global default."""
    if not is_admin(message):
        return
    from ..config import set_global_default
    defaults = get_global_defaults()
    new_value = not defaults["working_status"]
    set_global_default("working_status", new_value)
    status = "● on" if new_value else "○ off"
    await telegram_queue.send(message.chat.id, f"Global working status: {status}")


@router.message(Command("exp_suggestions"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_exp_suggestions(message: Message, telegram_queue: TelegramQueue):
    """Toggle feat_suggestions global default."""
    if not is_admin(message):
        return
    from ..config import set_global_default
    defaults = get_global_defaults()
    new_value = not defaults["feat_suggestions"]
    set_global_default("feat_suggestions", new_value)
    status = "● on" if new_value else "○ off"
    await telegram_queue.send(message.chat.id, f"Global suggestions: {status}")


@router.message(Command("exp_avatar_pack"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_exp_avatar_pack(message: Message, telegram_queue: TelegramQueue):
    """Toggle feat_avatar_pack global default."""
    if not is_admin(message):
        return
    from ..config import set_global_default
    defaults = get_global_defaults()
    new_value = not defaults["feat_avatar_pack"]
    set_global_default("feat_avatar_pack", new_value)
    status = "● on" if new_value else "○ off"
    await telegram_queue.send(message.chat.id, f"Global avatar pack: {status}")


@router.message(Command("verbose_mode"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_verbose_mode(message: Message, telegram_queue: TelegramQueue):
    """Show verbose mode menu for global defaults."""
    if not is_admin(message):
        return
    from ..telegram.keyboards.verbose_menu import verbose_menu_keyboard_dm
    from ..handlers.settings.verbose_menu import _build_verbose_text

    defaults = get_global_defaults()
    text = _build_verbose_text(defaults["display_mode"], defaults["line_limit"])
    kb = verbose_menu_keyboard_dm(defaults["display_mode"], defaults["line_limit"])
    await telegram_queue.send(message.chat.id, text, reply_markup=kb)


@router.message(Command("reset_to_default"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_reset_to_default(message: Message, telegram_queue: TelegramQueue):
    """Reset ALL threads to global defaults."""
    if not is_admin(message):
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes", callback_data="reset:all:yes"),
            InlineKeyboardButton(text="No", callback_data="reset:all:no"),
        ]
    ])
    await telegram_queue.send(message.chat.id, strings.RESET_ALL_CONFIRM, reply_markup=kb)


# ===== DM settings callbacks =====

@router.callback_query(F.data == "dmset:noop")
async def callback_dm_settings_noop(callback: CallbackQuery):
    """Handle placeholder button press."""
    await callback.answer()


@router.callback_query(F.data == "dmset:close")
async def callback_dm_settings_close(callback: CallbackQuery):
    """Close DM settings message."""
    if callback.message:
        await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith("dmset:page:"))
async def callback_dm_settings_page(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle DM settings page navigation."""
    from ..telegram.keyboards.settings import settings_keyboard_dm

    try:
        new_page = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer("Invalid page")
        return

    text = _build_dm_settings_text()
    kb = settings_keyboard_dm(page=new_page)
    await telegram_queue.edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("dmset:"))
async def callback_dm_settings(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle DM settings button presses."""
    from ..telegram.keyboards.settings import settings_keyboard_dm, SETTINGS_BUTTON_GROUPS_DM, _COMMAND_TO_ACTION
    from ..telegram.keyboards.verbose_menu import verbose_menu_keyboard_dm
    from ..handlers.settings.verbose_menu import _build_verbose_text
    from ..config import set_global_default

    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("Invalid callback")
        return

    action = parts[1]
    defaults = get_global_defaults()

    # Map action to setting key
    action_to_key = {
        "aa": "auto_accept",
        "rm": "response_mode",
        "db": "display_bullet",
        "dt": "display_thinking_text",
        "ws": "working_status",
        "es": "feat_suggestions",
        "ea": "feat_avatar_pack",
    }

    if action == "v":
        # Open verbose mode menu
        text = _build_verbose_text(defaults["display_mode"], defaults["line_limit"])
        kb = verbose_menu_keyboard_dm(defaults["display_mode"], defaults["line_limit"])
        await telegram_queue.edit(callback.message, text, reply_markup=kb)
        await callback.answer()
        return
    elif action == "rm":
        # Cycle response mode
        modes = ["all", "polite", "mentions"]
        current = defaults["response_mode"]
        try:
            next_idx = (modes.index(current) + 1) % len(modes)
        except ValueError:
            next_idx = 0
        set_global_default("response_mode", modes[next_idx])
        await callback.answer(f"Response: {modes[next_idx]}")
    elif action in action_to_key:
        key = action_to_key[action]
        new_value = not defaults[key]
        set_global_default(key, new_value)
        status = "● on" if new_value else "○ off"

        labels = {
            "auto_accept": "Auto-accept",
            "display_bullet": "Bullet prefix",
            "display_thinking_text": "Thinking text",
            "working_status": "Working status",
            "feat_suggestions": "Suggestions",
            "feat_avatar_pack": "Avatar pack",
        }
        label = labels.get(key, key)
        await callback.answer(f"{label}: {status}")
    else:
        await callback.answer("Unknown action")
        return

    # Determine current page
    current_page = 0
    action_to_cmd = {v: k for k, v in _COMMAND_TO_ACTION.items()}
    if action in action_to_cmd:
        cmd = action_to_cmd[action]
        for i, group in enumerate(SETTINGS_BUTTON_GROUPS_DM):
            if cmd in group:
                current_page = i
                break

    # Update message
    text = _build_dm_settings_text()
    kb = settings_keyboard_dm(page=current_page)
    await telegram_queue.edit(callback.message, text, reply_markup=kb)


# ===== DM verbose menu callbacks =====

@router.callback_query(F.data == "dmvm:noop")
async def callback_dm_verbose_noop(callback: CallbackQuery):
    """Handle placeholder button press."""
    await callback.answer()


@router.callback_query(F.data == "dmvm:back")
async def callback_dm_verbose_back(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Return to DM settings from verbose menu."""
    from ..telegram.keyboards.settings import settings_keyboard_dm

    text = _build_dm_settings_text()
    kb = settings_keyboard_dm(page=1)  # Page 1 has verbose_mode
    await telegram_queue.edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("dmvm:mode:"))
async def callback_dm_verbose_mode(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle verbose mode change in DM."""
    from ..telegram.keyboards.verbose_menu import verbose_menu_keyboard_dm
    from ..handlers.settings.verbose_menu import _build_verbose_text
    from ..config import set_global_default

    new_mode = callback.data.split(":")[-1]
    defaults = get_global_defaults()

    set_global_default("display_mode", new_mode)

    text = _build_verbose_text(new_mode, defaults["line_limit"])
    kb = verbose_menu_keyboard_dm(new_mode, defaults["line_limit"])
    await telegram_queue.edit(callback.message, text, reply_markup=kb)
    await callback.answer(f"Mode: {new_mode}")


@router.callback_query(F.data.startswith("dmvm:lines:"))
async def callback_dm_verbose_lines(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle line limit change in DM."""
    from ..telegram.keyboards.verbose_menu import verbose_menu_keyboard_dm
    from ..handlers.settings.verbose_menu import _build_verbose_text
    from ..config import set_global_default

    delta = int(callback.data.split(":")[-1])
    defaults = get_global_defaults()

    new_limit = max(1, defaults["line_limit"] + delta)
    set_global_default("line_limit", new_limit)
    set_global_default("display_mode", "lines")  # Switch to lines mode

    text = _build_verbose_text("lines", new_limit)
    kb = verbose_menu_keyboard_dm("lines", new_limit)
    await telegram_queue.edit(callback.message, text, reply_markup=kb)
    await callback.answer(f"Lines: {new_limit}")


# ===== Catch-all for other DM commands =====

@router.message(F.chat.type == ChatType.PRIVATE, F.text.startswith("/"))
async def cmd_dm_fallback(message: Message, telegram_queue: TelegramQueue):
    """Handle unknown commands in DM."""
    if not is_admin(message):
        return

    await telegram_queue.send(message.chat.id, strings.DM_UNKNOWN_COMMAND)
