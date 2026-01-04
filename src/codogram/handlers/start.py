"""Start flow handlers - /start, /restart and related callbacks."""
import asyncio

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ..domain.states import StartFlow, RestartFlow
from ..services.start_flow import StartFlowService, FlowAction, FlowResult
from ..session_manager import project_manager
from ..start_flow import (
    dir_not_found_keyboard,
    git_setup_keyboard,
    git_visibility_keyboard,
    restart_confirm_keyboard,
)
from ..tmux_selector import create_tmux_selection_keyboard

router = Router(name="start")


# ===== Result Handlers =====

async def _handle_result(
    message: Message,
    state: FSMContext,
    result: FlowResult,
):
    """Map FlowResult to Telegram response for messages."""
    match result.action:
        case FlowAction.ASK_PROJECT_NAME:
            await state.set_state(StartFlow.awaiting_project_name)
            if result.thread_id:
                await state.update_data(thread_id=result.thread_id)
            await message.answer("Отправь имя проекта:")

        case FlowAction.ASK_DIR_CHOICE:
            await state.set_state(StartFlow.awaiting_dir_choice)
            await state.update_data(project=result.project, path=result.path)
            await message.answer(
                f"Директория `{result.path}` не найдена.\n\nЧто делать?",
                reply_markup=dir_not_found_keyboard(),
                parse_mode="Markdown",
            )

        case FlowAction.ASK_GIT_CHOICE:
            await state.set_state(StartFlow.awaiting_git_choice)
            await state.update_data(project=result.project, path=result.path)
            await message.answer(
                "Git setup?",
                reply_markup=git_setup_keyboard(),
            )

        case FlowAction.ASK_LAUNCH_CONFIRM:
            await state.set_state(StartFlow.awaiting_launch_confirm)
            await state.update_data(project=result.project, path=result.path)
            from ..start_flow import launch_confirm_keyboard
            await message.answer(
                f"Запустить Claude в `{result.path}`?",
                reply_markup=launch_confirm_keyboard(),
                parse_mode="Markdown",
            )

        case FlowAction.SHOW_STATUS:
            await state.clear()
            await message.answer(
                f"Claude running: `{result.project}` in `{result.tmux_session}`",
                parse_mode="Markdown",
            )

        case FlowAction.CONNECT:
            await state.clear()
            await _connect_to_session(message, result)

        case FlowAction.LAUNCH:
            await state.clear()
            await _launch_claude(message, result)

        case FlowAction.SELECT_TMUX:
            await message.answer(
                "Multiple tmux sessions found. Select one:",
                reply_markup=create_tmux_selection_keyboard(
                    result.tmux_list, result.project
                ),
            )

        case FlowAction.ERROR:
            await state.clear()
            await message.answer(f"Error: {result.error}")

        case FlowAction.CANCELLED:
            await state.clear()
            await message.answer("Cancelled.")

        # Thread-specific actions
        case FlowAction.THREAD_SHOW_STATUS:
            await state.clear()
            await message.answer(
                f"Thread `{result.thread_name}` running in `{result.tmux_session}`",
                parse_mode="Markdown",
            )

        case FlowAction.THREAD_LAUNCH:
            await state.clear()
            await _launch_claude_in_thread(message, result)

        case FlowAction.UPGRADE_PENDING_THREAD:
            await state.clear()
            await message.answer(
                f"Thread upgraded to `{result.thread_name}`",
                parse_mode="Markdown",
            )
            await _launch_claude_in_thread(message, result)

        case FlowAction.REGISTER_UNKNOWN_TOPIC:
            await state.clear()
            await message.answer(
                f"Topic registered as `{result.thread_name}`",
                parse_mode="Markdown",
            )
            await _launch_claude_in_thread(message, result)


async def _handle_callback_result(
    callback: CallbackQuery,
    state: FSMContext,
    result: FlowResult,
):
    """Map FlowResult to Telegram response for callbacks."""
    await callback.answer()

    match result.action:
        case FlowAction.ASK_GIT_CHOICE:
            await state.set_state(StartFlow.awaiting_git_choice)
            await state.update_data(project=result.project, path=result.path)
            await callback.message.edit_text(
                "Git setup?",
                reply_markup=git_setup_keyboard(),
            )

        case FlowAction.LAUNCH:
            await state.clear()
            await callback.message.edit_text("Launching Claude...")
            await _launch_claude_from_callback(callback, result)

        case FlowAction.CONNECT:
            await state.clear()
            await callback.message.edit_text(
                f"Connected to `{result.tmux_session}`",
                parse_mode="Markdown",
            )
            await _connect_to_session_from_callback(callback, result)

        case FlowAction.ERROR:
            await state.clear()
            await callback.message.edit_text(f"Error: {result.error}")

        case FlowAction.RESTART_DONE:
            await state.clear()
            await callback.message.edit_text("Session killed. Use /start to restart.")

        case FlowAction.CANCELLED:
            await state.clear()
            await callback.message.edit_text("Cancelled.")


# ===== Launch Helpers =====

async def _launch_claude(message: Message, result: FlowResult):
    """Launch Claude session from message context."""
    from ..launch_animation import launch_with_animation
    from ..main import telegram_queue

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("Project not found")
        return

    thread = project.get_or_create_thread(None, "main")

    if thread.launch_task and not thread.launch_task.done():
        await message.answer("Launch already in progress")
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=message.bot,
            chat_id=message.chat.id,
            thread_id=None,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )


async def _launch_claude_from_callback(callback: CallbackQuery, result: FlowResult):
    """Launch Claude session from callback context."""
    from ..launch_animation import launch_with_animation
    from ..main import telegram_queue

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        return

    thread = project.get_or_create_thread(None, "main")

    if thread.launch_task and not thread.launch_task.done():
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            thread_id=None,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )


async def _launch_claude_in_thread(message: Message, result: FlowResult):
    """Launch Claude in a specific thread."""
    from ..launch_animation import launch_with_animation
    from ..main import telegram_queue

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        return

    thread = project.threads.get(result.thread_id)
    if not thread:
        return

    if thread.launch_task and not thread.launch_task.done():
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=message.bot,
            chat_id=message.chat.id,
            thread_id=result.thread_id,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )


async def _connect_to_session(message: Message, result: FlowResult):
    """Connect to existing tmux session."""
    project = project_manager.get_by_chat(message.chat.id)
    if project:
        project.tmux_session = result.tmux_session
        project_manager._save()
        await message.answer(
            f"Connected to `{result.tmux_session}`",
            parse_mode="Markdown",
        )


async def _connect_to_session_from_callback(callback: CallbackQuery, result: FlowResult):
    """Connect to existing tmux session from callback."""
    project = project_manager.get_by_chat(callback.message.chat.id)
    if project:
        project.tmux_session = result.tmux_session
        project_manager._save()


# ===== Commands =====

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    start_flow = StartFlowService(project_manager, None)

    args = message.text.split()[1:] if message.text else []
    thread_id = message.message_thread_id

    result = start_flow.handle_start(
        chat_id=message.chat.id,
        args=args,
        chat_title=message.chat.title,
        thread_id=thread_id,
    )

    await _handle_result(message, state, result)


# ===== FSM State Handlers =====

@router.message(StartFlow.awaiting_project_name)
async def on_project_name(message: Message, state: FSMContext):
    """Handle project name input."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    thread_id = data.get("thread_id")

    result = start_flow.handle_project_name(message.chat.id, message.text.strip())

    # If thread flow, preserve thread_id in result
    if thread_id and result.thread_id is None:
        result.thread_id = thread_id

    await _handle_result(message, state, result)


@router.message(StartFlow.awaiting_custom_path)
async def on_custom_path(message: Message, state: FSMContext):
    """Handle custom path input."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_custom_path(
        message.chat.id,
        data["project"],
        message.text.strip(),
    )

    await _handle_result(message, state, result)


@router.message(StartFlow.awaiting_clone_url)
async def on_clone_url(message: Message, state: FSMContext):
    """Handle git clone URL input."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_clone_url(
        message.chat.id,
        data["project"],
        data["path"],
        message.text.strip(),
    )

    await _handle_result(message, state, result)
