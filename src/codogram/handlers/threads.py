"""Thread management: create and delete forum topics."""
import subprocess

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import require_forum_group, _flow_state
from ..magic_names import get_random_magic_name
from ..services.launch import create_thread_with_session

router = Router(name="threads")


# ===== /thread_delete =====

@router.message(Command("thread_delete"))
async def cmd_thread_delete(message: Message, telegram_queue: TelegramQueue):
    """Close current thread and its Claude session."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    if thread_id is None:
        await telegram_queue.reply(message, "This command can only be used in a topic")
        return

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "Project not found")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await telegram_queue.reply(message, "This topic is not linked to a Claude session")
        return

    # Confirmation
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes, delete", callback_data=f"thread_delete:{thread_id}"),
            InlineKeyboardButton(text="Cancel", callback_data="thread_delete:cancel"),
        ]
    ])
    await telegram_queue.reply(
        message,
        f"Delete thread '{thread.name}'?\n"
        "Topic and tmux session will be deleted.",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("thread_delete:"))
async def on_thread_delete_callback(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle thread close confirmation."""
    data = callback.data.split(":")[1]
    if data == "cancel":
        await telegram_queue.edit(callback.message, "Cancelled")
        await callback.answer()
        return

    thread_id = int(data)
    chat_id = callback.message.chat.id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    # Stop tasks
    if thread.watcher_task:
        thread.watcher_task.cancel()
    if thread.poller_task:
        thread.poller_task.cancel()
    if thread.binding_task:
        thread.binding_task.cancel()

    # Kill tmux
    tmux_name = thread.get_tmux_session(project.project_name)
    subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Delete topic
    try:
        await callback.bot.delete_forum_topic(chat_id, thread_id)
    except Exception as e:
        await telegram_queue.edit(callback.message, f"Error deleting topic: {e}")
        await callback.answer()
        return

    # Remove from project
    del project.threads[thread_id]
    project_manager._save()

    await callback.answer("Thread closed")


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
        _flow_state[chat_id] = {
            "state": "thread_create_pending",
            "name": name,
        }
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
    state = _flow_state.get(chat_id)

    if not state or state.get("state") != "thread_create_pending":
        await callback.answer("Session expired")
        return

    name = state.get("name")
    _flow_state.pop(chat_id, None)

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
