# src/codogram/handlers/start/callbacks.py
"""Callback handlers for start flow."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from ...domain.states import StartFlow
from ...services.start import StartFlowService, FlowAction, FlowResult
from ...core.session_manager import project_manager
from ...telegram.queue import TelegramQueue
from ...start_flow import git_visibility_keyboard
from ... import strings
from .helpers import get_state_data
from .launch import launch_claude_from_callback, handle_wr_recreate, handle_wr_create, handle_wr_main, handle_wr_cancel

router = Router(name="start_callbacks")


# === Directory Choice Callbacks ===

@router.callback_query(F.data == "start:create_dir")
async def on_create_dir(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle create directory button."""
    data = await get_state_data(state, callback, telegram_queue, "project", "path")
    if not data:
        return

    service = StartFlowService(project_manager)
    result = service.handle_create_dir(data["project"], data["path"])

    await _handle_callback_result(callback, state, result, telegram_queue)


@router.callback_query(F.data == "start:custom_path")
async def on_custom_path_btn(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle custom path button."""
    await state.set_state(StartFlow.awaiting_custom_path)
    await telegram_queue.edit(callback.message, strings.START_PATH_PROMPT, parse_mode=None)
    await callback.answer()


# === Git Setup Callbacks ===

@router.callback_query(F.data == "start:git_init")
async def on_git_init(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle git init button."""
    data = await get_state_data(state, callback, telegram_queue, "project", "path")
    if not data:
        return

    service = StartFlowService(project_manager)
    result = service.handle_git_init(
        callback.message.chat.id,
        data["project"],
        data["path"],
    )

    await _handle_callback_result(callback, state, result, telegram_queue)


@router.callback_query(F.data == "start:git_gh")
async def on_git_gh(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle git + gh button."""
    await state.set_state(StartFlow.awaiting_gh_visibility)
    await telegram_queue.edit(
        callback.message,
        strings.START_GIT_VISIBILITY_PROMPT,
        reply_markup=git_visibility_keyboard(),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data.in_({"start:gh_private", "start:gh_public"}))
async def on_gh_visibility(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle GitHub visibility choice."""
    data = await get_state_data(state, callback, telegram_queue, "project", "path")
    if not data:
        return

    service = StartFlowService(project_manager)
    private = callback.data == "start:gh_private"
    result = service.handle_gh_create(
        callback.message.chat.id,
        data["project"],
        data["path"],
        private,
    )

    await _handle_callback_result(callback, state, result, telegram_queue)


@router.callback_query(F.data == "start:git_clone")
async def on_git_clone(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle git clone button."""
    await state.set_state(StartFlow.awaiting_clone_url)
    await telegram_queue.edit(callback.message, strings.START_CLONE_URL_PROMPT)
    await callback.answer()


@router.callback_query(F.data == "start:no_git")
async def on_no_git(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle no git button."""
    data = await get_state_data(state, callback, telegram_queue, "project", "path")
    if not data:
        return

    service = StartFlowService(project_manager)
    result = service.handle_no_git(
        callback.message.chat.id,
        data["project"],
        data["path"],
    )

    await _handle_callback_result(callback, state, result, telegram_queue)


# === Launch Callbacks ===

@router.callback_query(F.data == "start:launch_claude")
async def on_launch_claude(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle launch Claude button."""
    data = await state.get_data()

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    await state.clear()
    await telegram_queue.edit(callback.message, strings.START_LAUNCHING, parse_mode=None)
    await callback.answer()

    result = FlowResult(
        action=FlowAction.LAUNCH,
        project=data.get("project"),
        path=data.get("path"),
    )
    await launch_claude_from_callback(callback, result, telegram_queue)


@router.callback_query(F.data == "start:cancel")
async def on_cancel(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle cancel button."""
    await state.clear()
    await telegram_queue.edit(callback.message, strings.CANCELLED, parse_mode=None)
    await callback.answer()


# === Tmux Selection Callbacks ===

@router.callback_query(F.data.startswith("select_tmux:"))
async def on_tmux_selected(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle tmux selection."""
    service = StartFlowService(project_manager)

    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer(strings.INVALID_CALLBACK)
        return

    project_name, tmux_session = parts[1], parts[2]
    result = service.handle_tmux_selected(
        callback.message.chat.id,
        project_name,
        tmux_session,
    )

    await _handle_callback_result(callback, state, result, telegram_queue)


# === Worktree Recovery Callbacks ===

@router.callback_query(F.data.startswith("wr_recreate:"))
async def on_wr_recreate(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle worktree recreate callback."""
    await handle_wr_recreate(callback, telegram_queue)


@router.callback_query(F.data.startswith("wr_create:"))
async def on_wr_create(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle worktree create callback."""
    await handle_wr_create(callback, telegram_queue)


@router.callback_query(F.data.startswith("wr_main:"))
async def on_wr_main(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle resume in main callback."""
    await handle_wr_main(callback, telegram_queue)


@router.callback_query(F.data.startswith("wr_cancel:"))
async def on_wr_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle worktree cancel callback."""
    await handle_wr_cancel(callback, telegram_queue)


# === Helper for callback results ===

async def _handle_callback_result(
    callback: CallbackQuery,
    state: FSMContext,
    result: FlowResult,
    telegram_queue: TelegramQueue,
):
    """Map FlowResult to Telegram response for callbacks."""
    from ...start_flow import git_setup_keyboard
    from .helpers import register_chat_menu

    await callback.answer()

    match result.action:
        case FlowAction.ASK_GIT_CHOICE:
            await state.set_state(StartFlow.awaiting_git_choice)
            await state.update_data(project=result.project, path=result.path)
            await telegram_queue.edit(
                callback.message,
                strings.START_GIT_SETUP_PROMPT,
                reply_markup=git_setup_keyboard(),
                parse_mode=None,
            )

        case FlowAction.LAUNCH:
            await state.clear()
            await telegram_queue.edit(callback.message, strings.START_LAUNCHING, parse_mode=None)
            await launch_claude_from_callback(callback, result, telegram_queue)

        case FlowAction.CONNECT:
            await state.clear()
            project = project_manager.get_by_chat(callback.message.chat.id)
            if project:
                project.tmux_session = result.tmux_session
                project_manager._save()
                await register_chat_menu(callback.bot, callback.message.chat)
            await telegram_queue.edit(
                callback.message,
                strings.START_CONNECTED.format(tmux_session=result.tmux_session),
            )

        case FlowAction.ERROR:
            await state.clear()
            await telegram_queue.edit(callback.message, strings.START_ERROR.format(error=result.error), parse_mode=None)

        case FlowAction.RESTART_DONE:
            await state.clear()
            await telegram_queue.edit(callback.message, strings.START_SESSION_KILLED, parse_mode=None)

        case FlowAction.CANCELLED:
            await state.clear()
            await telegram_queue.edit(callback.message, strings.CANCELLED, parse_mode=None)

        case FlowAction.ASK_CLONE_URL_RETRY:
            # Stay in awaiting_clone_url state - don't clear, let user retry
            await telegram_queue.edit(
                callback.message,
                f"{result.error}\n\n{strings.GIT_URL_RETRY_PROMPT}",
            )
