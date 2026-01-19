"""DM-specific handlers for onboarding and dashboard."""
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_NOT_MEMBER, ADMINISTRATOR, MEMBER
from aiogram.enums import ChatType

from .. import strings
from ..config import get_user_onboarded, set_user_onboarded, settings
from ..keyboards.dm_onboarding import (
    carousel_keyboard,
    validation_recheck_keyboard,
    dashboard_keyboard,
)
from ..services.dm_onboarding import (
    get_slide_content,
    get_total_slides,
    format_validation_checks,
    run_critical_checks,
    run_warning_checks,
)
from ..services.dashboard import format_dashboard, ProjectInfo
from ..session_manager import project_manager
from ..project_launcher import is_tmux_session_exists
from ..telegram_queue import TelegramQueue

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
    msg_to_edit = callback.message if edit_existing else None

    # 1. Show "checking" message
    if msg_to_edit:
        await telegram_queue.edit(msg_to_edit, strings.DM_VALIDATION_CHECKING)
    else:
        await telegram_queue.send(chat_id, strings.DM_VALIDATION_CHECKING)

    # 2. Run critical checks
    critical_results = run_critical_checks()
    critical_errors = [r for r in critical_results if not r.ok]

    # 3. Format all checks with [v] or [x]
    checks_text = format_validation_checks(critical_results)

    if critical_errors:
        # Show errors with recheck button
        text = strings.DM_VALIDATION_ERROR.format(checks=checks_text)
        keyboard = validation_recheck_keyboard()
        if msg_to_edit:
            await telegram_queue.edit(msg_to_edit, text, reply_markup=keyboard)
        else:
            await telegram_queue.send(chat_id, text, reply_markup=keyboard)
        return

    # 4. Run warning checks and add to checks display
    warning_results = run_warning_checks()
    all_checks_text = checks_text + "\n" + format_validation_checks(warning_results)

    # 5. Show success with all checks (critical + warnings)
    full_text = strings.DM_VALIDATION_OK.format(checks=all_checks_text)

    if msg_to_edit:
        await telegram_queue.edit(msg_to_edit, full_text)
    else:
        await telegram_queue.send(chat_id, full_text)

    # 6. Send SEPARATE CTA message
    bot_info = await callback.bot.get_me()
    cta_text = strings.DM_CTA.format(bot_username=bot_info.username)
    await telegram_queue.send(chat_id, cta_text)

    # Mark user as onboarded
    set_user_onboarded(callback.from_user.id)


@router.callback_query(F.data == "onb:recheck")
async def on_recheck(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle recheck validation button."""
    if not callback.message:
        await callback.answer()
        return

    await show_validation(callback, telegram_queue, edit_existing=True)
    await callback.answer()


# ===== /intro =====

@router.message(Command("intro"), F.chat.type == ChatType.PRIVATE)
async def cmd_intro(message: Message, telegram_queue: TelegramQueue):
    """Show onboarding again."""
    if not is_admin(message):
        return

    await run_onboarding(message, telegram_queue)


# ===== /dash =====

@router.message(Command("dash"), F.chat.type == ChatType.PRIVATE)
async def cmd_dash(message: Message, telegram_queue: TelegramQueue, bot: Bot):
    """Show dashboard with all projects."""
    if not is_admin(message):
        return

    await show_dashboard(message.chat.id, telegram_queue, bot)


async def show_dashboard(chat_id: int, telegram_queue: TelegramQueue, bot: Bot):
    """Render and send dashboard."""
    # Gather project info
    projects_list = []
    for project in project_manager.projects.values():
        if not project.chat_id:
            continue

        try:
            chat = await bot.get_chat(project.chat_id)
            member_count = await bot.get_chat_member_count(project.chat_id)

            # Count active tmux sessions for this project
            active = 0
            for t in project.threads.values():
                tmux_name = t.get_tmux_session(project.project_name)
                if is_tmux_session_exists(tmux_name):
                    active += 1

            # Get creator from chat administrators
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
            # Skip projects we can't access
            continue

    text = format_dashboard(projects_list)
    keyboard = dashboard_keyboard()
    await telegram_queue.send(chat_id, text, reply_markup=keyboard)


@router.callback_query(F.data == "dash:refresh")
async def on_dash_refresh(callback: CallbackQuery, telegram_queue: TelegramQueue, bot: Bot):
    """Handle dashboard refresh."""
    if not callback.message:
        await callback.answer()
        return

    await show_dashboard(callback.message.chat.id, telegram_queue, bot)
    await callback.answer("Refreshed")


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


# ===== Catch-all for other DM commands =====

@router.message(F.chat.type == ChatType.PRIVATE, F.text.startswith("/"))
async def cmd_dm_fallback(message: Message, telegram_queue: TelegramQueue):
    """Handle unknown commands in DM."""
    if not is_admin(message):
        return

    await telegram_queue.send(message.chat.id, strings.DM_UNKNOWN_COMMAND)
