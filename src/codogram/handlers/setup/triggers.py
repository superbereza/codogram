# src/codogram/handlers/setup/triggers.py
"""Setup flow trigger handlers.

Entry points (per design):
1. my_chat_member: bot added to chat or granted admin
2. /start in chat without registered project
3. Any message in chat without registered project
"""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, ChatMemberUpdated, Message

from ...domain.states import SetupFlow
from ...session_manager import ProjectManager, ProjectState, project_manager
from ...services.setup import check_bot_admin_rights, check_base_dir
from ...keyboards.setup import admin_check_keyboard, setup_type_keyboard
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_triggers")


class ProjectNotRegistered(BaseFilter):
    """Filter that passes only if chat has no registered project."""

    async def __call__(self, message: Message) -> bool:
        pm = ProjectManager()
        result = pm.get_by_chat(message.chat.id) is None
        logger.debug(f"ProjectNotRegistered filter: chat={message.chat.id}, result={result}")
        return result


class NotInSetupFlow(BaseFilter):
    """Filter that passes only if NOT in SetupFlow state.

    Used to prevent on_any_message from intercepting allowed commands
    during setup (like /reset_all).
    """

    async def __call__(self, message: Message, state: FSMContext) -> bool:
        current_state = await state.get_state()
        return not (current_state and current_state.startswith("SetupFlow:"))


def _is_group_chat(chat_type: str) -> bool:
    """Check if chat type is a group (not private/channel)."""
    return chat_type in ("group", "supergroup")


def _is_project_registered(chat_id: int) -> bool:
    """Check if chat has a registered project."""
    pm = ProjectManager()
    return pm.get_by_chat(chat_id) is not None


def _find_project_by_title(title: str) -> ProjectState | None:
    """Find project where project_name matches chat title.

    Used for migration detection when my_chat_member arrives before migrate_to_chat_id.
    """
    for p in project_manager.projects.values():
        if p.project_name == title:
            return p
    return None


def _find_project_by_old_chat_id(chat_id: int) -> ProjectState | None:
    """Find project where old_chat_id matches.

    Used for migration detection after migrate_to_chat_id already processed.
    """
    for p in project_manager.projects.values():
        if p.old_chat_id == chat_id:
            return p
    return None


# --- Entry Point 1: Bot added to chat ---

@router.my_chat_member(
    F.new_chat_member.status.in_({"member", "administrator"})
)
async def on_bot_added(event: ChatMemberUpdated, state: FSMContext, telegram_queue):
    """Handle bot being added to chat or granted admin rights."""
    chat = event.chat
    old_status = event.old_chat_member.status if event.old_chat_member else None

    # Only trigger on actual addition (from left/kicked/restricted to member/admin)
    # Skip if this is just a promotion (member -> administrator)
    if old_status in {"member", "administrator"}:
        logger.debug(f"Bot status changed but not added: {old_status} -> {event.new_chat_member.status}")
        return

    # Block private chats
    if chat.type == "private":
        await event.answer(strings.SETUP_PRIVATE_CHAT)
        return

    # Block channels
    if chat.type == "channel":
        await event.answer(strings.SETUP_CHANNEL_NOT_SUPPORTED)
        return

    # Check if setup already in progress
    current_state = await state.get_state()
    if current_state and current_state.startswith("SetupFlow:"):
        logger.debug(f"Setup already in progress for chat {chat.id}")
        return

    # Check if project already registered
    if _is_project_registered(chat.id):
        logger.debug(f"Project already registered for chat {chat.id}")
        return

    # --- Migration detection for supergroups ---
    if chat.type == "supergroup":
        # 1. Check by old_chat_id (if migrate_to_chat_id already processed)
        project = _find_project_by_old_chat_id(chat.id)
        if project:
            logger.info(f"Migration detected by old_chat_id: {chat.id}")
            await _handle_migrated_project(event.bot, chat, project, telegram_queue)
            return

        # 2. Check by title (if migrate_to_chat_id not yet processed)
        project = _find_project_by_title(chat.title)
        if project:
            logger.info(f"Migration detected by title: {chat.title}")
            project.old_chat_id = project.chat_id
            project.chat_id = chat.id
            project_manager._save()
            await _handle_migrated_project(event.bot, chat, project, telegram_queue)
            return

        # 3. Delay fallback - wait for migrate_to_chat_id event
        logger.debug(f"Supergroup without project, waiting 2s for migration event: {chat.id}")
        await asyncio.sleep(2)

        # Recheck after delay
        if _is_project_registered(chat.id):
            logger.info(f"Migration detected after delay for chat {chat.id}")
            project = project_manager.get_by_chat(chat.id)
            if project and project.awaiting_admin_rights:
                # Migration handler already set the flag, nothing more to do
                return
            return

    await _start_setup_flow(event.bot, chat, state)


async def _handle_migrated_project(bot: Bot, chat: Chat, project: ProjectState, telegram_queue):
    """Handle project after migration detected - check admin rights."""
    from ...telegram_queue import OutgoingBatch
    from ...services.menu import register_menu_for_chat

    has_rights = await check_bot_admin_rights(bot, chat.id)

    if not has_rights:
        project.awaiting_admin_rights = True
        project_manager._save()
        logger.info(f"Migration awaiting admin: {project.project_name}")

        batch = OutgoingBatch(
            chat_id=chat.id,
            thread_id=None,
            messages=[{"text": strings.MIGRATION_ADMIN_REQUIRED}],
        )
        await telegram_queue.enqueue(batch)
        return

    # Has rights - register menu
    project.awaiting_admin_rights = False
    project_manager._save()
    await register_menu_for_chat(bot, chat.id, is_forum=True)

    batch = OutgoingBatch(
        chat_id=chat.id,
        thread_id=None,
        messages=[{"text": strings.MIGRATION_SUCCESS}],
    )
    await telegram_queue.enqueue(batch)


# --- Entry Point 2: /start in unregistered chat ---

@router.message(
    Command("start", ignore_case=True),
    F.chat.type.in_({"group", "supergroup"}),
    ProjectNotRegistered(),
)
async def on_start_command(message: Message, state: FSMContext):
    """Handle /start command in group chats without project."""
    logger.info(f"on_start_command triggered, chat={message.chat.id}")
    chat = message.chat

    # Check if setup already in progress
    current_state = await state.get_state()
    logger.info(f"Current state: {current_state}")
    if current_state and current_state.startswith("SetupFlow:"):
        # /start during setup restarts the flow (per design line 535)
        logger.info("Clearing state for restart")
        await state.clear()

    await _start_setup_flow(message.bot, chat, state)


# --- Entry Point 3: Any message in unregistered chat ---

@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    ProjectNotRegistered(),
    NotInSetupFlow(),
)
async def on_any_message(message: Message, state: FSMContext):
    """Handle any message in group chat without project.

    This is a catch-all that triggers setup if no project registered.
    Must be registered LAST to not intercept other handlers.

    Note: NotInSetupFlow filter ensures we don't match during setup,
    allowing commands like /reset_all to reach their handlers.
    """
    await _start_setup_flow(message.bot, message.chat, state)


# --- Shared setup start logic ---

async def _start_setup_flow(bot: Bot, chat: Chat, state: FSMContext):
    """Start the setup flow - check base_dir first, then admin rights."""
    # Check base_dir FIRST
    base_path = check_base_dir()
    if not base_path:
        await bot.send_message(
            chat.id,
            strings.SETUP_BASE_DIR_MISSING,
            parse_mode="MarkdownV2",
        )
        return  # Flow blocked

    # Register SETUP_COMMANDS menu for this chat
    from ...services.menu import SETUP_COMMANDS
    from aiogram.types import BotCommandScopeChat

    scope = BotCommandScopeChat(chat_id=chat.id)
    try:
        await bot.set_my_commands(SETUP_COMMANDS, scope=scope)
    except Exception as e:
        logger.warning(f"Failed to set setup menu: {e}")

    # Check admin rights
    has_rights = await check_bot_admin_rights(bot, chat.id)

    if not has_rights:
        # Ask for admin rights
        await state.set_state(SetupFlow.awaiting_admin_rights)
        await bot.send_message(
            chat.id,
            strings.SETUP_ADMIN_REQUIRED,
            reply_markup=admin_check_keyboard(),
            parse_mode="MarkdownV2",
        )
        return

    # Has rights - show setup type selection
    await state.set_state(SetupFlow.awaiting_setup_type)
    await bot.send_message(
        chat.id,
        strings.SETUP_CHOOSE_TYPE,
        reply_markup=setup_type_keyboard(),
    )
