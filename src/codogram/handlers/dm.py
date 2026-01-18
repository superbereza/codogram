"""DM-specific handlers for onboarding and dashboard."""
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
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
    format_validation_errors,
    format_validation_warnings,
    run_critical_checks,
    run_warning_checks,
)
from ..services.dashboard import format_dashboard, ProjectInfo
from ..session_manager import project_manager
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
    # Count projects and sessions
    projects = project_manager.projects
    project_count = len(projects)
    session_count = sum(
        1 for p in projects.values()
        if any(
            t.session_id for t in p.threads.values()
        )
    )

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


async def show_validation(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Show validation results after carousel."""
    # Run critical checks
    critical_results = run_critical_checks()
    critical_errors = [r for r in critical_results if not r.ok]

    if critical_errors:
        # Show errors with recheck button
        error_text = format_validation_errors(critical_errors)
        text = strings.DM_VALIDATION_ERROR.format(errors=error_text)
        keyboard = validation_recheck_keyboard()
        await telegram_queue.edit(
            callback.message,
            text,
            reply_markup=keyboard,
        )
        return

    # Run warning checks
    warning_results = run_warning_checks()
    warnings = [r for r in warning_results if not r.ok]

    # Show success + optional warnings + CTA
    bot_info = await callback.bot.get_me()
    cta_text = strings.DM_CTA.format(bot_username=bot_info.username)

    if warnings:
        warning_text = format_validation_warnings(warnings)
        full_text = f"{strings.DM_VALIDATION_OK}\n\n{strings.DM_VALIDATION_WARNINGS.format(warnings=warning_text)}\n\n{cta_text}"
    else:
        full_text = f"{strings.DM_VALIDATION_OK}\n\n{cta_text}"

    await telegram_queue.edit(
        callback.message,
        full_text,
        parse_mode="Markdown",
    )

    # Mark user as onboarded
    set_user_onboarded(callback.from_user.id)


@router.callback_query(F.data == "onb:recheck")
async def on_recheck(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle recheck validation button."""
    if not callback.message:
        await callback.answer()
        return

    await show_validation(callback, telegram_queue)
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

            # Count active sessions for this project
            active = sum(
                1 for t in project.threads.values()
                if t.session_id
            )

            # Get creator - might not always be available
            creator = "unknown"

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
