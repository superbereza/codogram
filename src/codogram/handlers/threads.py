"""Thread management: create and delete forum topics."""
import subprocess

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager

router = Router(name="threads")


# ===== /thread_delete =====

@router.message(Command("thread_delete"))
async def cmd_thread_delete(message: Message):
    """Close current thread and its Claude session."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    if thread_id is None:
        await message.answer("This command can only be used in a topic")
        return

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("Project not found")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await message.answer("This topic is not linked to a Claude session")
        return

    # Confirmation
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes, delete", callback_data=f"thread_delete:{thread_id}"),
            InlineKeyboardButton(text="Cancel", callback_data="thread_delete:cancel"),
        ]
    ])
    await message.answer(
        f"Delete thread '{thread.name}'?\n"
        "Topic and tmux session will be deleted.",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("thread_delete:"))
async def on_thread_delete_callback(callback: CallbackQuery):
    """Handle thread close confirmation."""
    data = callback.data.split(":")[1]
    if data == "cancel":
        await callback.message.edit_text("Cancelled")
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
        await callback.message.edit_text(f"Error deleting topic: {e}")
        await callback.answer()
        return

    # Remove from project
    del project.threads[thread_id]
    project_manager._save()

    await callback.answer("Thread closed")
