"""Handler for group -> supergroup migration event."""
from aiogram import Router, F
from aiogram.types import ChatMemberUpdated, Message

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue, OutgoingBatch
from ..services.menu import register_menu_for_chat
from ..services.setup import check_bot_admin_rights
from ..logging_config import logger
from .. import strings

router = Router(name="migration")


@router.message(F.migrate_to_chat_id)
async def on_chat_migration(message: Message, telegram_queue: TelegramQueue) -> None:
    """Handle chat migration when topics are enabled.

    Telegram changes chat_id when converting group to supergroup (forum).
    This handler updates the project's chat_id and registers extended menu.
    """
    old_chat_id = message.chat.id
    new_chat_id = message.migrate_to_chat_id

    logger.info(f"migration_detected: old={old_chat_id} new={new_chat_id}")

    # Find project by old chat_id
    project = project_manager.get_by_chat(old_chat_id)
    if not project:
        logger.debug(f"migration_ignored: no project for chat={old_chat_id}")
        return

    # Update chat_id, save old for race condition detection
    project.old_chat_id = old_chat_id
    project.chat_id = new_chat_id
    project_manager._save()
    logger.info(f"migration_updated: project={project.project_name} new_chat_id={new_chat_id}")

    # Check admin rights in new chat
    has_rights = await check_bot_admin_rights(message.bot, new_chat_id)

    if not has_rights:
        # Block until admin rights granted
        project.awaiting_admin_rights = True
        project_manager._save()
        logger.info(f"migration_awaiting_admin: project={project.project_name}")

        batch = OutgoingBatch(
            chat_id=new_chat_id,
            thread_id=None,
            messages=[{"text": strings.MIGRATION_ADMIN_REQUIRED}],
        )
        await telegram_queue.enqueue(batch)
        return

    # Has rights - register menu and send success notification
    await register_menu_for_chat(message.bot, new_chat_id, is_forum=True)

    batch = OutgoingBatch(
        chat_id=new_chat_id,
        thread_id=None,
        messages=[{"text": strings.MIGRATION_SUCCESS}],
    )
    await telegram_queue.enqueue(batch)


@router.my_chat_member(F.new_chat_member.status == "administrator")
async def on_admin_rights_granted(event: ChatMemberUpdated, telegram_queue: TelegramQueue) -> None:
    """Handle bot being granted admin rights after migration.

    This handler catches the case when:
    1. Group migrated to supergroup
    2. Bot lost admin rights
    3. User granted admin rights back

    Note: This is separate from SetupFlow.awaiting_admin_rights handler
    which handles initial setup. This handles post-migration rights grant.
    """
    chat = event.chat
    project = project_manager.get_by_chat(chat.id)

    if not project:
        return

    if not project.awaiting_admin_rights:
        return

    # Verify we actually have rights now
    has_rights = await check_bot_admin_rights(event.bot, chat.id)
    if not has_rights:
        logger.warning(f"Admin granted event but no rights: {chat.id}")
        return

    # Clear the flag
    project.awaiting_admin_rights = False
    project_manager._save()
    logger.info(f"Admin rights granted after migration: {project.project_name}")

    # Register extended menu
    await register_menu_for_chat(event.bot, chat.id, is_forum=True)

    # Send success notification
    batch = OutgoingBatch(
        chat_id=chat.id,
        thread_id=None,
        messages=[{"text": strings.ADMIN_RIGHTS_GRANTED}],
    )
    await telegram_queue.enqueue(batch)
