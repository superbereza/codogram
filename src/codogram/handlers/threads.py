"""Thread management: create and delete forum topics."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import require_forum_group, set_flow_state, get_flow_state, clear_flow_state
from ..magic_names import get_random_magic_name
from ..services.launch import create_thread_with_session

router = Router(name="threads")


@router.message(Command("thread"))
async def cmd_thread(message: Message, telegram_queue: TelegramQueue):
    """Alias for /thread_create."""
    await cmd_thread_create(message, telegram_queue)


@router.message(Command("thread_delete"))
async def cmd_thread_delete(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish."""
    await telegram_queue.reply(message, "`[i]` Use /finish to archive topics")


# ===== /thread_create =====

@router.message(Command("thread_create"))
async def cmd_thread_create(message: Message, telegram_queue: TelegramQueue):
    """Create a new thread (topic) with its own Claude session."""
    if not await require_forum_group(message, telegram_queue):
        return

    chat_id = message.chat.id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "Project not found. Use /start first")
        return

    # Parse optional name from command
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        name = args[1].strip().lower()
    else:
        existing_names = {t.name for t in project.threads.values()}
        name = get_random_magic_name(existing_names)

    # Check if any non-worktree threads exist (excluding main)
    non_worktree_threads = [
        t for t in project.threads.values()
        if t.thread_id is not None and not t.worktree_path
    ]

    if non_worktree_threads:
        # Store pending thread name for confirmation
        set_flow_state(chat_id, message.message_thread_id, {
            "type": "thread_create_pending",
            "name": name,
        })
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create in main repo", callback_data="thread_create_confirm")],
            [InlineKeyboardButton(text="Use /branch_create instead", callback_data="branch_create_redirect")],
            [InlineKeyboardButton(text="Cancel", callback_data="cancel")]
        ])
        await telegram_queue.reply(
            message,
            "Non-worktree threads exist. For isolated work, consider /branch_create.\n"
            "Create thread in main repo anyway?",
            reply_markup=keyboard
        )
        return

    # Create directly
    thread = await create_thread_with_session(
        bot=message.bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )

    if not thread:
        await telegram_queue.reply(message, "Error creating topic")


@router.callback_query(F.data == "thread_create_confirm")
async def on_thread_create_confirm(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle thread_create confirmation (create in main anyway)."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    state = get_flow_state(chat_id, thread_id)

    if not state or state.get("type") != "thread_create_pending":
        await callback.answer("Session expired")
        return

    name = state.get("name")
    clear_flow_state(chat_id, thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    await callback.message.delete()

    thread = await create_thread_with_session(
        bot=callback.bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )

    if not thread:
        await telegram_queue.send(chat_id, "Error creating topic")

    await callback.answer()
