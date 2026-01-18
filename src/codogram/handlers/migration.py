"""Handler for group -> supergroup migration event."""
import asyncio

from aiogram import Bot, Router, F
from aiogram.types import Message

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue, OutgoingBatch
from ..services.menu import register_menu_for_chat
from ..adapters.sticker import StickerAdapter
from ..services.emoji_pack import EmojiPackService
from ..logging_config import logger
from .. import strings

router = Router(name="migration")

# TODO: Move to strings.py when centralizing message strings
MIGRATION_MESSAGE = """`[v]` Topics enabled

Multi-session mode unlocked:
/thread - new topic, same directory
/branch - isolated feature branch + topic
/finish - merge and archive"""


async def _create_emoji_pack_background(bot: Bot, chat_id: int, telegram_queue: TelegramQueue) -> None:
    """Create emoji pack in background after migration."""
    try:
        # Wait a bit for migration to complete
        await asyncio.sleep(2)

        # Get participants (admins for now)
        admins = await bot.get_chat_administrators(chat_id)
        participants = [admin.user for admin in admins if not admin.user.is_bot]

        if not participants:
            logger.warning(f"No participants for emoji pack in chat {chat_id}")
            return

        # Create service with adapter (layered architecture)
        adapter = StickerAdapter(bot)
        service = EmojiPackService(adapter)
        pack_name = await service.create_pack(chat_id, participants)

        if pack_name:
            pack_link = f"t.me/addemoji/{pack_name}"
            batch = OutgoingBatch(
                chat_id=chat_id,
                thread_id=None,
                messages=[{"text": strings.EMOJI_PACK_CREATED.format(pack_link=pack_link)}],
            )
            await telegram_queue.enqueue(batch)
            logger.info(f"Emoji pack created on migration: {pack_name}")
    except Exception as e:
        logger.error(f"Failed to create emoji pack on migration: {e}")


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

    # Create emoji pack asynchronously
    asyncio.create_task(
        _create_emoji_pack_background(message.bot, new_chat_id, telegram_queue)
    )
