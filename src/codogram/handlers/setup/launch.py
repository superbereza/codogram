# src/codogram/handlers/setup/launch.py
"""Launch phase handler with rename confirmation."""
import asyncio
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from ...domain.states import SetupFlow
from ...telegram.keyboards.setup import go_back_keyboard
from ...services.setup import check_bot_admin_rights
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_launch")


def _rename_confirm_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for rename confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes", callback_data="setup:rename_yes"),
            InlineKeyboardButton(text="Skip", callback_data="setup:rename_skip"),
        ],
    ])


@router.callback_query(F.data == "error:retry")
async def on_error_retry(callback: CallbackQuery, state: FSMContext):
    """Retry setup after error."""
    await callback.answer()

    # Clear state and restart setup
    await state.clear()

    # Restart setup flow
    from .triggers import _start_setup_flow
    await _start_setup_flow(callback.bot, callback.message.chat, state)


async def do_launch(message: Message, state: FSMContext):
    """Start the launch phase - check if rename needed first.

    This is called from various flows after all setup is complete.
    """
    data = await state.get_data()
    project_name = data["project_name"]

    chat = message.chat
    chat_title = chat.title or ""

    # Check if rename needed (only for supergroups where bot can rename)
    if chat.type == "supergroup":
        has_rights = await check_bot_admin_rights(message.bot, chat.id)

        if has_rights and chat_title != project_name:
            # Offer rename confirmation
            await state.set_state(SetupFlow.awaiting_rename_confirm)
            await message.edit_text(
                strings.SETUP_RENAME_PROMPT.format(name=project_name),
                reply_markup=_rename_confirm_keyboard(),
                parse_mode="MarkdownV2",
            )
            return

    # No rename needed - proceed to launch
    await _execute_launch(message, state)


@router.callback_query(
    SetupFlow.awaiting_rename_confirm,
    F.data == "setup:rename_yes"
)
async def on_rename_yes(callback: CallbackQuery, state: FSMContext):
    """Handle rename confirmation."""
    await callback.answer()

    data = await state.get_data()
    project_name = data["project_name"]
    chat = callback.message.chat

    # Try to rename
    try:
        await callback.bot.set_chat_title(chat.id, project_name)
        logger.info(f"Chat renamed during setup: {chat.title} -> {project_name}")
    except Exception as e:
        logger.warning(f"Failed to rename chat during setup: {e}")
        # Show warning but continue
        await callback.message.edit_text(
            strings.SETUP_RENAME_FAILED,
            reply_markup=None,
            parse_mode="MarkdownV2",
        )
        await asyncio.sleep(1.5)

    # Proceed to launch
    await _execute_launch(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_rename_confirm,
    F.data == "setup:rename_skip"
)
async def on_rename_skip(callback: CallbackQuery, state: FSMContext):
    """Handle rename skip."""
    await callback.answer()

    # Proceed to launch
    await _execute_launch(callback.message, state)


async def _execute_launch(message: Message, state: FSMContext):
    """Execute the actual launch (after rename decision)."""
    # Lazy imports to avoid circular dependencies
    from ...services.setup.init_project import init_project
    from ...services.menu import register_menu_for_chat
    from ...telegram.launch_animation import launch_with_animation
    from ...session_manager import project_manager
    from ...main import telegram_queue

    # Enter launching state (blocks user input)
    await state.set_state(SetupFlow.launching)

    data = await state.get_data()

    # Delete previous bot message (git choice, rename prompt, etc.)
    if prev_msg_id := data.get("bot_message_id"):
        try:
            await message.bot.delete_message(message.chat.id, prev_msg_id)
        except Exception:
            pass  # Message might already be deleted

    project_name = data["project_name"]
    target_dir = Path(data["target_dir"])

    chat = message.chat
    chat_id = chat.id
    chat_type = chat.type
    thread_id = message.message_thread_id

    # Initialize project (creates dir, registers in config)
    result = await init_project(
        project_name=project_name,
        target_dir=target_dir,
        chat_id=chat_id,
    )

    if not result.success:
        # Reset to setup type selection so user can retry
        await state.set_state(SetupFlow.awaiting_setup_type)
        await message.answer(
            f"{strings.STATUS_ERR} Setup failed: {result.error}",
            reply_markup=go_back_keyboard("error:retry"),
            parse_mode="MarkdownV2",
        )
        return

    # Register appropriate menu
    is_forum = chat_type == "supergroup" and getattr(chat, "is_forum", False)
    await register_menu_for_chat(message.bot, chat_id, is_forum)

    # Clear FSM state
    await state.clear()

    # Get project and thread for animation
    project = project_manager.get_by_chat(chat_id)
    thread_name = project_name if thread_id else "main"
    thread = project.get_or_create_thread(thread_id, thread_name)

    # Launch Claude with animation (this handles everything including success message)
    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=message.bot,
            chat_id=chat_id,
            thread_id=thread_id,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )

    # Create emoji pack in background if feature enabled AND supergroup
    # (emoji pack is for topic icons, only makes sense in forums)
    if project.feat_avatar_pack and chat_type == "supergroup":
        asyncio.create_task(
            _create_emoji_pack_background(message.bot, chat_id, telegram_queue)
        )


async def _create_emoji_pack_background(bot, chat_id: int, telegram_queue) -> None:
    """Create emoji pack in background after setup.

    Only called when feat_avatar_pack is enabled.
    """
    from ...telegram.sticker import StickerAdapter
    from ...services.emoji_pack import EmojiPackService
    from ...telegram.queue import OutgoingBatch

    try:
        # Wait for setup to complete
        await asyncio.sleep(3)

        # Get participants (admins for now)
        try:
            admins = await bot.get_chat_administrators(chat_id)
            participants = [admin.user for admin in admins if not admin.user.is_bot]
        except Exception:
            participants = []

        if not participants:
            logger.warning(f"No participants for emoji pack in chat {chat_id}")
            return

        # Create service with adapter
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
            logger.info(f"Emoji pack created on setup: {pack_name}")
    except Exception as e:
        logger.exception(f"Failed to create emoji pack on setup: {e}")
