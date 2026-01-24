# src/codogram/handlers/start/commands.py
"""Start command handler."""
from pathlib import Path

from aiogram import Router
from aiogram.types import Message
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ...core.session_manager import project_manager
from ...domain.worktree_state import WorktreeState, get_worktree_state
from ...telegram.keyboards.keyboards import worktree_recovery_keyboard
from ...services.start import StartFlowService
from ...telegram.queue import TelegramQueue, OutgoingBatch
from ... import strings
from ..common import normalize_thread_id
from .registry import dispatch_result
from .launch import launch_claude, launch_claude_in_thread

router = Router(name="start_commands")


@router.message(Command("start", ignore_case=True))
async def cmd_start(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle /start command."""
    if message.chat.type == ChatType.PRIVATE:
        return  # DM handled by dm.py

    thread_id = normalize_thread_id(message.chat, message.message_thread_id)

    # Check for stale worktree in topic
    if thread_id is not None:
        project = project_manager.get_by_chat(message.chat.id)
        if project:
            thread = project.threads.get(thread_id)
            if thread and thread.worktree_path:
                wt_state = get_worktree_state(thread, Path(project.cwd))
                if wt_state != WorktreeState.OK:
                    try:
                        relative_path = Path(thread.worktree_path).relative_to(Path(project.cwd))
                    except ValueError:
                        relative_path = thread.worktree_path

                    text = (strings.START_WORKTREE_NOT_FOUND_BRANCH_EXISTS
                            if wt_state == WorktreeState.MISSING_WITH_BRANCH
                            else strings.START_WORKTREE_NOT_FOUND_BRANCH_MISSING
                    ).format(path=relative_path, branch=thread.name)

                    batch = OutgoingBatch(
                        chat_id=message.chat.id,
                        thread_id=thread.thread_id,
                        messages=[{"text": text}],
                        reply_markup=worktree_recovery_keyboard(thread.thread_id, wt_state),
                    )
                    await telegram_queue.enqueue(batch)
                    return

    service = StartFlowService(project_manager)
    args = message.text.split()[1:] if message.text else []
    result = service.handle_start(
        chat_id=message.chat.id,
        args=args,
        chat_title=message.chat.title,
        thread_id=thread_id,
    )

    async def launch_cb(msg, res, queue, thread=False):
        if thread:
            await launch_claude_in_thread(msg, res, queue)
        else:
            await launch_claude(msg, res, queue)

    await dispatch_result(message, state, result, telegram_queue, launch_cb)
