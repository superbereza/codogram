# src/codogram/handlers/setup/triggers.py
"""Setup flow trigger handlers.

Entry points (per design):
1. my_chat_member: bot added to chat or granted admin
2. /start in chat without registered project
3. Any message in chat without registered project
"""
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, ChatMemberUpdated, Message

from ...domain.states import SetupFlow
from ...core.session_manager import project_manager
from ...services.setup import check_bot_admin_rights, check_base_dir
from ...services.group_auth import GroupAuthService
from ...telegram.keyboards.setup import admin_check_keyboard, setup_type_keyboard
from ... import strings

logger = logging.getLogger(__name__)

# In-memory guard against concurrent setup flows
# Python GIL makes set operations atomic
_setup_in_progress: set[int] = set()

router = Router(name="setup_triggers")


class ProjectNotRegistered(BaseFilter):
    """Filter that passes only if chat has no registered project."""

    async def __call__(self, message: Message) -> bool:
        result = project_manager.get_by_chat(message.chat.id) is None
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


class SetupNotInProgress(BaseFilter):
    """Filter that passes only if chat is NOT currently starting setup."""

    async def __call__(self, message: Message) -> bool:
        return message.chat.id not in _setup_in_progress


def _is_group_chat(chat_type: str) -> bool:
    """Check if chat type is a group (not private/channel)."""
    return chat_type in ("group", "supergroup")


def _is_project_registered(chat_id: int) -> bool:
    """Check if chat has a registered project."""
    return project_manager.get_by_chat(chat_id) is not None


# --- Entry Point 1: Bot added to chat ---

@router.my_chat_member(
    F.new_chat_member.status.in_({"member", "administrator"})
)
async def on_bot_added(event: ChatMemberUpdated, state: FSMContext, group_auth: GroupAuthService):
    """Handle bot being added to chat or granted admin rights."""
    chat = event.chat
    old_status = event.old_chat_member.status if event.old_chat_member else None

    # Only trigger on actual addition (from left/kicked/restricted to member/admin)
    # Skip if this is just a promotion (member -> administrator)
    if old_status in {"member", "administrator"}:
        logger.debug(f"Bot status changed but not added: {old_status} -> {event.new_chat_member.status}")
        return

    # Guard against race with on_any_message
    if chat.id in _setup_in_progress:
        logger.debug(f"Setup already starting for chat {chat.id}")
        return

    # Block private chats
    if chat.type == "private":
        await event.answer(strings.SETUP_PRIVATE_CHAT)
        return

    # Block channels
    if chat.type == "channel":
        await event.answer(strings.SETUP_CHANNEL_NOT_SUPPORTED)
        return

    # Check group authorization (must have admin from ADMIN_IDS)
    # Note: Don't send ERR_GROUP_NOT_ALLOWED here - AdminMiddleware handles rejection
    # for any subsequent messages. Sending here would cause duplicate messages.
    if chat.type in ("group", "supergroup"):
        registered = await group_auth.check_and_register(event.bot, chat.id)
        if not registered:
            logger.info(f"group_not_authorized: chat_id={chat.id}")
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

    await _start_setup_flow(event.bot, chat, state)


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
    SetupNotInProgress(),  # Prevent race with on_bot_added
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
    # Guard against concurrent calls
    if chat.id in _setup_in_progress:
        logger.debug(f"Setup already in progress for chat {chat.id}")
        return

    _setup_in_progress.add(chat.id)
    try:
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

        # For supergroups, check admin rights (needed for rename chat, manage topics)
        # For regular groups, skip - these features don't apply
        if chat.type == "supergroup":
            has_rights = await check_bot_admin_rights(bot, chat.id)

            if not has_rights:
                # Ask for admin rights
                await state.set_state(SetupFlow.awaiting_admin_rights)
                await state.update_data(chat_title=chat.title or "")
                await bot.send_message(
                    chat.id,
                    strings.SETUP_ADMIN_REQUIRED,
                    reply_markup=admin_check_keyboard(),
                    parse_mode="MarkdownV2",
                )
                return

        # Has rights (supergroup) or regular group - show setup type selection
        await state.set_state(SetupFlow.awaiting_setup_type)
        await state.update_data(chat_title=chat.title or "")
        await bot.send_message(
            chat.id,
            strings.SETUP_CHOOSE_TYPE,
            reply_markup=setup_type_keyboard(),
        )
    finally:
        _setup_in_progress.discard(chat.id)
