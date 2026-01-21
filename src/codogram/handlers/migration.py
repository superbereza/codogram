"""Handler for group -> supergroup migration event."""
import asyncio

from aiogram import Bot, Router, F
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..core.session_manager import project_manager
from ..telegram.queue import TelegramQueue, OutgoingBatch, DeleteBatch
from ..services.menu import register_menu_for_chat
from ..services.setup import check_bot_admin_rights
from ..telegram.sticker import StickerAdapter
from ..services.emoji_pack import EmojiPackService
from ..logging_config import logger
from .. import strings

router = Router(name="migration")


def _migration_check_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with Check rights button for migration."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_CHECK_RIGHTS, callback_data="migration:check_admin")],
    ])


def _rename_confirm_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for rename confirmation after migration."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes", callback_data="migration:rename_yes"),
            InlineKeyboardButton(text="Skip", callback_data="migration:rename_skip"),
        ],
    ])


async def _create_emoji_pack_background(bot: Bot, chat_id: int, telegram_queue: TelegramQueue) -> None:
    """Create emoji pack in background after migration.

    Only called when bot has admin rights.
    """
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
                messages=[{"text": strings.EMOJI_PACK_CREATED.format(pack_link=pack_link), "parse_mode": "MarkdownV2"}],
            )
            await telegram_queue.enqueue(batch)
            logger.info(f"Emoji pack created on migration: {pack_name}")
    except Exception as e:
        logger.exception(f"Failed to create emoji pack on migration: {e}")


async def _send_migration_success(bot: Bot, chat_id: int, telegram_queue: TelegramQueue) -> None:
    """Send migration success message and create emoji pack."""
    batch = OutgoingBatch(
        chat_id=chat_id,
        thread_id=None,
        messages=[{"text": strings.MIGRATION_SUCCESS, "parse_mode": "MarkdownV2"}],
    )
    await telegram_queue.enqueue(batch)

    # Create emoji pack asynchronously
    asyncio.create_task(
        _create_emoji_pack_background(bot, chat_id, telegram_queue)
    )


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
            messages=[{"text": strings.MIGRATION_ADMIN_REQUIRED, "parse_mode": "MarkdownV2"}],
            reply_markup=_migration_check_keyboard(),
            replace_key=f"migration_admin:{new_chat_id}",
        )
        await telegram_queue.enqueue(batch)
        return

    # Has rights - register menu and send success notification
    await register_menu_for_chat(message.bot, new_chat_id, is_forum=True)

    batch = OutgoingBatch(
        chat_id=new_chat_id,
        thread_id=None,
        messages=[{"text": strings.MIGRATION_SUCCESS, "parse_mode": "MarkdownV2"}],
    )
    await telegram_queue.enqueue(batch)

    # Create emoji pack asynchronously (only if has rights)
    asyncio.create_task(
        _create_emoji_pack_background(message.bot, new_chat_id, telegram_queue)
    )


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

    # Delete the "admin required" message
    delete_batch = DeleteBatch(
        chat_id=chat.id,
        message_id=0,
        replace_key=f"migration_admin:{chat.id}",
    )
    await telegram_queue.enqueue(delete_batch)

    # Check if rename needed (chat title differs from project name)
    chat_title = chat.title or ""
    if chat_title != project.project_name:
        # Ask for confirmation
        batch = OutgoingBatch(
            chat_id=chat.id,
            thread_id=None,
            messages=[{"text": strings.SETUP_RENAME_PROMPT.format(name=project.project_name), "parse_mode": "MarkdownV2"}],
            reply_markup=_rename_confirm_keyboard(),
        )
        await telegram_queue.enqueue(batch)
        return

    # No rename needed - send success and create emoji pack
    await _send_migration_success(event.bot, chat.id, telegram_queue)


@router.callback_query(F.data == "migration:check_admin")
async def on_check_admin_rights(callback: CallbackQuery, telegram_queue: TelegramQueue) -> None:
    """Handle Check rights button press after migration."""
    chat = callback.message.chat
    project = project_manager.get_by_chat(chat.id)

    if not project:
        await callback.answer("No project found")
        return

    if not project.awaiting_admin_rights:
        await callback.answer("Already configured")
        return

    # Check if rights were granted
    has_rights = await check_bot_admin_rights(callback.bot, chat.id)

    if not has_rights:
        await callback.answer(strings.SETUP_ADMIN_CHECK_FAILED, show_alert=True)
        return

    await callback.answer()

    # Clear the flag
    project.awaiting_admin_rights = False
    project_manager._save()
    logger.info(f"Admin rights granted via check button: {project.project_name}")

    # Register extended menu
    await register_menu_for_chat(callback.bot, chat.id, is_forum=True)

    # Delete the admin required message
    await callback.message.delete()

    # Check if rename needed (chat title differs from project name)
    chat_title = chat.title or ""
    if chat_title != project.project_name:
        # Ask for confirmation
        batch = OutgoingBatch(
            chat_id=chat.id,
            thread_id=None,
            messages=[{"text": strings.SETUP_RENAME_PROMPT.format(name=project.project_name), "parse_mode": "MarkdownV2"}],
            reply_markup=_rename_confirm_keyboard(),
        )
        await telegram_queue.enqueue(batch)
        return

    # No rename needed - send success and create emoji pack
    await _send_migration_success(callback.bot, chat.id, telegram_queue)


@router.callback_query(F.data == "migration:rename_yes")
async def on_rename_yes(callback: CallbackQuery, telegram_queue: TelegramQueue) -> None:
    """Handle rename confirmation after migration."""
    chat = callback.message.chat
    project = project_manager.get_by_chat(chat.id)

    if not project:
        await callback.answer("No project found")
        return

    await callback.answer()

    # Try to rename
    try:
        await callback.bot.set_chat_title(chat.id, project.project_name)
        logger.info(f"Chat renamed after migration: {chat.title} -> {project.project_name}")
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Failed to rename chat after migration: {e}")
        await callback.message.edit_text(
            strings.SETUP_RENAME_FAILED,
            reply_markup=None,
            parse_mode="MarkdownV2",
        )

    # Send success and create emoji pack
    await _send_migration_success(callback.bot, chat.id, telegram_queue)


@router.callback_query(F.data == "migration:rename_skip")
async def on_rename_skip(callback: CallbackQuery, telegram_queue: TelegramQueue) -> None:
    """Handle rename skip after migration."""
    chat = callback.message.chat

    await callback.answer()
    await callback.message.delete()

    # Send success and create emoji pack
    await _send_migration_success(callback.bot, chat.id, telegram_queue)
