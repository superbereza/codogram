# src/codogram/handlers/reset/handlers.py
"""Reset handlers - simple, no FlowAction enum."""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ...core.session_manager import project_manager
from ...domain.states import ResetFlow
from ...services.reset import ResetService
from ...telegram.keyboards.reset import (
    reset_confirm_keyboard,
    reset_dir_choice_keyboard,
    reset_uncommitted_keyboard,
)
from ...telegram.queue import TelegramQueue
from ...git.utils import has_uncommitted_changes
from ... import strings
from ..common import normalize_thread_id

router = Router(name="reset")


@router.message(Command("hard_reset", "reset_all", ignore_case=True))
async def cmd_hard_reset(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle /hard_reset command (full project reset)."""
    # Check if start flow is in progress (e.g., clone running)
    current_state = await state.get_state()
    if current_state and str(current_state).startswith("StartFlow:"):
        await telegram_queue.reply(message, strings.RESET_FLOW_IN_PROGRESS)
        return

    # Check if setup flow is in progress - cancel it
    if current_state and str(current_state).startswith("SetupFlow:"):
        await state.clear()
        await telegram_queue.reply(message, strings.SETUP_CANCELLED)
        return

    project = project_manager.get_by_chat(message.chat.id)

    # No project registered
    if not project:
        await telegram_queue.reply(message, strings.RESET_NO_PROJECT)
        return

    service = ResetService(project_manager)

    # Setup phase - reset immediately
    if service.is_setup_phase(project):
        result = service.cleanup(project, delete_directory=True)
        if result.success:
            await telegram_queue.reply(message, strings.RESET_COMPLETE)
        else:
            await telegram_queue.reply(message, result.error)
        return

    # Working project - ask for confirmation
    await state.set_state(ResetFlow.awaiting_confirm)
    await state.update_data(project_name=project.project_name)

    # Different message if called from topic
    if message.message_thread_id:
        text = strings.RESET_CONFIRM_TOPIC.format(name=project.project_name)
    else:
        text = strings.RESET_CONFIRM.format(name=project.project_name)

    await telegram_queue.reply(message, text, reply_markup=reset_confirm_keyboard())


@router.callback_query(F.data == "reset:continue")
async def on_reset_continue(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle reset confirm -> continue."""
    current_state = await state.get_state()
    if current_state != ResetFlow.awaiting_confirm:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    data = await state.get_data()
    project_name = data.get("project_name")
    if not project_name:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    project = project_manager.projects.get(project_name)
    service = ResetService(project_manager)

    if not project or not project.cwd:
        service.cleanup(project, delete_directory=False)
        await state.clear()
        await telegram_queue.edit(
            callback.message,
            strings.RESET_DONE.format(dir_status="not found"),
        )
        await callback.answer()
        return

    # Directory exists - check for uncommitted changes
    await state.set_state(ResetFlow.awaiting_dir_choice)

    if has_uncommitted_changes(Path(project.cwd)):
        await telegram_queue.edit(
            callback.message,
            strings.RESET_UNCOMMITTED.format(path=project.cwd),
            reply_markup=reset_uncommitted_keyboard(),
        )
    else:
        await telegram_queue.edit(
            callback.message,
            strings.RESET_DIR_CHOICE.format(path=project.cwd),
            reply_markup=reset_dir_choice_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "reset:keep")
async def on_reset_keep(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle reset -> keep directory."""
    current_state = await state.get_state()
    if current_state != ResetFlow.awaiting_dir_choice:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    data = await state.get_data()
    project_name = data.get("project_name")
    if not project_name:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    project = project_manager.projects.get(project_name)
    if not project:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    service = ResetService(project_manager)
    service.cleanup(project, delete_directory=False)

    await state.clear()
    await telegram_queue.edit(
        callback.message,
        strings.RESET_DONE.format(dir_status=f"kept at `{project.cwd}`"),
    )
    await callback.answer()


@router.callback_query(F.data == "reset:delete")
async def on_reset_delete(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle reset -> delete directory."""
    current_state = await state.get_state()
    if current_state != ResetFlow.awaiting_dir_choice:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    data = await state.get_data()
    project_name = data.get("project_name")
    if not project_name:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    project = project_manager.projects.get(project_name)
    if not project:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    service = ResetService(project_manager)
    result = service.cleanup(project, delete_directory=True)

    await state.clear()

    if result.success:
        await telegram_queue.edit(
            callback.message,
            strings.RESET_DONE.format(dir_status="deleted"),
        )
    else:
        await telegram_queue.edit(callback.message, result.error)
    await callback.answer()


@router.callback_query(F.data == "reset:back")
async def on_reset_back(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle reset -> go back."""
    current_state = await state.get_state()
    if current_state != ResetFlow.awaiting_dir_choice:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    data = await state.get_data()
    project_name = data.get("project_name")
    if not project_name:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    # Go back to confirm step
    await state.set_state(ResetFlow.awaiting_confirm)

    text = strings.RESET_CONFIRM.format(name=project_name)
    await telegram_queue.edit(
        callback.message,
        text,
        reply_markup=reset_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "reset:cancel")
async def on_reset_cancel(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle reset -> cancel."""
    await state.clear()
    await telegram_queue.edit(callback.message, strings.CANCELLED, parse_mode=None)
    await callback.answer()
