# src/codogram/handlers/restart/handlers.py
"""Restart handlers - simple, no FlowAction enum."""
import asyncio
from pathlib import Path
import subprocess

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ...core.session_manager import project_manager
from ...domain.states import RestartFlow
from ...services.restart import RestartService
from ...start_flow import restart_confirm_keyboard
from ...telegram.queue import TelegramQueue
from ... import strings
from ..common import normalize_thread_id
from ..start.helpers import parse_callback_data, parse_thread_id

router = Router(name="restart")


@router.message(Command("reset_chat", "restart", ignore_case=True))
async def cmd_restart(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle /restart command."""
    service = RestartService(project_manager)
    thread_id = normalize_thread_id(message.chat, message.message_thread_id)

    tmux_name = service.get_session_to_restart(message.chat.id, thread_id)
    if not tmux_name:
        await telegram_queue.reply(message, strings.CLAUDE_NO_RESTART, parse_mode=None)
        return

    await state.set_state(RestartFlow.awaiting_confirm)
    await state.update_data(tmux_session=tmux_name, thread_id=thread_id)
    await telegram_queue.reply(
        message,
        strings.START_RESTART_CONFIRM.format(tmux_session=tmux_name),
        reply_markup=restart_confirm_keyboard(),
    )


@router.callback_query(F.data == "restart:confirm")
async def on_restart_confirm(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle restart confirmation."""
    data = await state.get_data()
    tmux_session = data.get("tmux_session")
    thread_id = data.get("thread_id")

    if not tmux_session:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    # Cancel background tasks
    project = project_manager.get_by_chat(callback.message.chat.id)
    if project:
        thread = project.get_thread(thread_id)
        if thread:
            for task in [thread.launch_task, thread.watcher_task, thread.poller_task, thread.binding_task]:
                if task and not task.done():
                    task.cancel()

    # Kill session
    service = RestartService(project_manager)
    service.kill_session(tmux_session)

    await state.clear()
    await telegram_queue.edit(callback.message, strings.START_SESSION_KILLED, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle restart cancel."""
    await state.clear()
    await telegram_queue.edit(callback.message, strings.CANCELLED, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("resume:"))
async def on_resume_callback(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle resume error recovery callbacks.

    BUG FIX: Safe parsing instead of crash on malformed callback data.
    """
    # Safe parsing instead of crash
    parts = parse_callback_data(callback.data, 3)
    if not parts:
        await callback.answer("Invalid callback data")
        return

    action = parts[1]
    thread_id = parse_thread_id(parts[2])

    # Validate thread_id if not "cancel"
    if action != "cancel" and parts[2] != "None" and thread_id is None:
        await callback.answer("Invalid thread ID")
        return

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    thread = project.threads.get(thread_id)

    if action == "start_new":
        if thread:
            thread.session_id = None
            thread.jsonl_path = None
            project_manager._save()

        await telegram_queue.edit(callback.message, strings.START_NEW_SESSION)
        await callback.answer()

        from ...telegram.launch_animation import launch_with_animation
        cwd = thread.worktree_path if thread and thread.has_valid_worktree() else None

        if thread:
            thread.launch_task = asyncio.create_task(
                launch_with_animation(
                    bot=callback.bot, chat_id=callback.message.chat.id,
                    thread_id=thread_id, project=project, thread=thread,
                    queue=telegram_queue, cwd=cwd,
                )
            )

    elif action == "recreate":
        if not thread:
            await callback.answer(strings.THREAD_NOT_FOUND)
            return

        # Validate branch_name
        branch_name = thread.name
        if not branch_name:
            await callback.answer("Thread has no branch name")
            return

        await telegram_queue.edit(callback.message, strings.START_RECREATING_WORKTREE)
        await callback.answer()

        main_repo = Path(project.cwd)
        worktree_path = main_repo / ".worktrees" / branch_name

        try:
            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            # BUG FIX: Use asyncio.to_thread for subprocess calls
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "worktree", "add", str(worktree_path), branch_name],
                cwd=str(main_repo), capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())

            thread.worktree_path = str(worktree_path)
            project_manager._save()
            await telegram_queue.edit(callback.message, strings.START_WORKTREE_RECREATED)
        except Exception as e:
            await telegram_queue.edit(callback.message,
                                      strings.START_WORKTREE_RECREATE_FAILED.format(error=e))

    elif action == "cancel":
        await telegram_queue.edit(callback.message, strings.CANCELLED)
        await callback.answer()
