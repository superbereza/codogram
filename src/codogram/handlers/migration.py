"""Handler for group -> supergroup migration event."""
from aiogram import Router, F
from aiogram.types import Message

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue, OutgoingBatch
from ..services.menu import register_menu_for_chat
from ..logging_config import logger

router = Router(name="migration")

# TODO: Move to strings.py when centralizing message strings
MIGRATION_MESSAGE = """`[v]` Topics enabled

Multi-session mode unlocked:
/thread - new topic, same directory
/branch - isolated feature branch + topic
/finish - merge and archive"""


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

    # Update chat_id
    project.chat_id = new_chat_id
    project_manager._save()
    logger.info(f"migration_updated: project={project.project_name} new_chat_id={new_chat_id}")

    # Register extended menu for forum
    await register_menu_for_chat(message.bot, new_chat_id, is_forum=True)

    # Send notification
    batch = OutgoingBatch(
        chat_id=new_chat_id,
        thread_id=None,
        messages=[{"text": MIGRATION_MESSAGE}],
    )
    await telegram_queue.enqueue(batch)
