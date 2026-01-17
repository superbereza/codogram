"""Thread management: create and delete forum topics."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from .. import strings
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import require_forum_group, set_flow_state, get_flow_state, clear_flow_state
from ..domain.create_flow import CreateType
from ..keyboards.create_flow import build_name_prompt_keyboard
from ..services.create_flow import create_flow_service
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
    name_arg = args[1].strip() if len(args) > 1 else None

    if create_flow_service.should_show_prompt(name_arg):
        set_flow_state(chat_id, message.message_thread_id, {
            "type": "awaiting_create_name",
            "create_type": "thread",
        })
        await telegram_queue.reply(
            message,
            "Thread name?\n\nSend name or pick random",
            reply_markup=build_name_prompt_keyboard(CreateType.THREAD),
        )
        return

    # Validate name
    name, error = create_flow_service.validate_name(name_arg, project)
    if error:
        await telegram_queue.reply(message, error)
        return

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
        await callback.answer(strings.SESSION_EXPIRED)
        return

    name = state.get("name")
    clear_flow_state(chat_id, thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.BRANCH_PROJECT_NOT_FOUND_TOAST)
        return

    # 1. Remove buttons (edit)
    await telegram_queue.edit(callback.message, strings.THREAD_CREATING.format(name=name))
    await callback.answer()

    # 2. Create thread
    thread = await create_thread_with_session(
        bot=callback.bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )

    # 3. Final status (send)
    if thread:
        await telegram_queue.send(chat_id, strings.THREAD_CREATED.format(name=name), thread_id=thread_id)
    else:
        await telegram_queue.send(chat_id, strings.CREATE_TOPIC_ERROR, thread_id=thread_id)
