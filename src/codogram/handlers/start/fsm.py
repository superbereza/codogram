# src/codogram/handlers/start/fsm.py
"""FSM state handlers for start flow."""
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from ...domain.states import StartFlow
from ...services.start import StartFlowService
from ...core.session_manager import project_manager
from ...telegram.queue import TelegramQueue
from ... import strings
from .helpers import get_state_data_msg
from .registry import dispatch_result
from .launch import launch_claude, launch_claude_in_thread

router = Router(name="start_fsm")


@router.message(StartFlow.awaiting_project_name)
async def on_project_name(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle project name input."""
    service = StartFlowService(project_manager)

    data = await state.get_data()
    thread_id = data.get("thread_id")

    result = service.handle_project_name(message.chat.id, message.text.strip())

    # If thread flow, preserve thread_id in result
    if thread_id and result.thread_id is None:
        result.thread_id = thread_id

    async def launch_cb(msg, res, queue, thread=False):
        if thread:
            await launch_claude_in_thread(msg, res, queue)
        else:
            await launch_claude(msg, res, queue)

    await dispatch_result(message, state, result, telegram_queue, launch_cb)


@router.message(StartFlow.awaiting_custom_path)
async def on_custom_path(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle custom path input."""
    data = await get_state_data_msg(state, message, telegram_queue, "project")
    if not data:
        return

    service = StartFlowService(project_manager)
    result = service.handle_custom_path(
        message.chat.id,
        data["project"],
        message.text.strip(),
    )

    async def launch_cb(msg, res, queue, thread=False):
        if thread:
            await launch_claude_in_thread(msg, res, queue)
        else:
            await launch_claude(msg, res, queue)

    await dispatch_result(message, state, result, telegram_queue, launch_cb)


@router.message(StartFlow.awaiting_clone_url)
async def on_clone_url(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle git clone URL input."""
    data = await get_state_data_msg(state, message, telegram_queue, "project", "path")
    if not data:
        return

    # Show progress before clone attempt (can take a while for large repos)
    await telegram_queue.reply(message, strings.CLONE_IN_PROGRESS)

    service = StartFlowService(project_manager)
    result = service.handle_clone_url(
        message.chat.id,
        data["project"],
        data["path"],
        message.text.strip(),
    )

    async def launch_cb(msg, res, queue, thread=False):
        if thread:
            await launch_claude_in_thread(msg, res, queue)
        else:
            await launch_claude(msg, res, queue)

    await dispatch_result(message, state, result, telegram_queue, launch_cb)
