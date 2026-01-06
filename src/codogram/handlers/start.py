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
from ..telegram_queue import TelegramQueue
from ..tmux_selector import create_tmux_selection_keyboard
from ..project_launcher import is_tmux_session_exists

router = Router(name="start")


# ===== Result Handlers =====

async def _handle_result(
    message: Message,
    state: FSMContext,
    result: FlowResult,
    telegram_queue: TelegramQueue,
):
    """Map FlowResult to Telegram response for messages."""
    match result.action:
        case FlowAction.ASK_PROJECT_NAME:
            await state.set_state(StartFlow.awaiting_project_name)
            if result.thread_id:
                await state.update_data(thread_id=result.thread_id)
            await telegram_queue.reply(message, "Отправь имя проекта:", parse_mode=None)

        case FlowAction.ASK_DIR_CHOICE:
            await state.set_state(StartFlow.awaiting_dir_choice)
            await state.update_data(project=result.project, path=result.path)
            await telegram_queue.reply(
                message,
                f"Директория `{result.path}` не найдена.\n\nЧто делать?",
                reply_markup=dir_not_found_keyboard(),
            )

        case FlowAction.ASK_GIT_CHOICE:
            await state.set_state(StartFlow.awaiting_git_choice)
            await state.update_data(project=result.project, path=result.path)
            await telegram_queue.reply(
                message,
                "Git setup?",
                reply_markup=git_setup_keyboard(),
                parse_mode=None,
            )

        case FlowAction.ASK_LAUNCH_CONFIRM:
            await state.set_state(StartFlow.awaiting_launch_confirm)
            await state.update_data(project=result.project, path=result.path)
            from ..start_flow import launch_confirm_keyboard
            await telegram_queue.reply(
                message,
                f"Запустить Claude в `{result.path}`?",
                reply_markup=launch_confirm_keyboard(),
            )

        case FlowAction.SHOW_STATUS:
            await state.clear()
            await telegram_queue.reply(
                message,
                f"Claude running: `{result.project}` in `{result.tmux_session}`",
            )

        case FlowAction.CONNECT:
            await state.clear()
            await _connect_to_session(message, result, telegram_queue)

        case FlowAction.LAUNCH:
            await state.clear()
            await _launch_claude(message, result, telegram_queue)

        case FlowAction.SELECT_TMUX:
            await telegram_queue.reply(
                message,
                "Multiple tmux sessions found. Select one:",
                reply_markup=create_tmux_selection_keyboard(
                    result.tmux_list, result.project
                ),
                parse_mode=None,
            )

        case FlowAction.ERROR:
            await state.clear()
            await telegram_queue.reply(message, f"Error: {result.error}", parse_mode=None)

        case FlowAction.CANCELLED:
            await state.clear()
            await telegram_queue.reply(message, "Cancelled.", parse_mode=None)

        # Thread-specific actions
        case FlowAction.THREAD_SHOW_STATUS:
            await state.clear()
            await telegram_queue.reply(
                message,
                f"Thread `{result.thread_name}` running in `{result.tmux_session}`",
            )

        case FlowAction.THREAD_LAUNCH:
            await state.clear()
            await _launch_claude_in_thread(message, result, telegram_queue)

        case FlowAction.UPGRADE_PENDING_THREAD:
            await state.clear()
            await telegram_queue.reply(
                message,
                f"Thread upgraded to `{result.thread_name}`",
            )
            await _launch_claude_in_thread(message, result, telegram_queue)

        case FlowAction.REGISTER_UNKNOWN_TOPIC:
            await state.clear()
            await telegram_queue.reply(
                message,
                f"Topic registered as `{result.thread_name}`",
            )
            await _launch_claude_in_thread(message, result, telegram_queue)


async def _handle_callback_result(
    callback: CallbackQuery,
    state: FSMContext,
    result: FlowResult,
    telegram_queue: TelegramQueue,
):
    """Map FlowResult to Telegram response for callbacks."""
    await callback.answer()

    match result.action:
        case FlowAction.ASK_GIT_CHOICE:
            await state.set_state(StartFlow.awaiting_git_choice)
            await state.update_data(project=result.project, path=result.path)
            await telegram_queue.edit(
                callback.message,
                "Git setup?",
                reply_markup=git_setup_keyboard(),
                parse_mode=None,
            )

        case FlowAction.LAUNCH:
            await state.clear()
            await telegram_queue.edit(callback.message, "Launching Claude...", parse_mode=None)
            await _launch_claude_from_callback(callback, result, telegram_queue)

        case FlowAction.CONNECT:
            await state.clear()
            await telegram_queue.edit(
                callback.message,
                f"Connected to `{result.tmux_session}`",
            )
            await _connect_to_session_from_callback(callback, result)

        case FlowAction.ERROR:
            await state.clear()
            await telegram_queue.edit(callback.message, f"Error: {result.error}", parse_mode=None)

        case FlowAction.RESTART_DONE:
            await state.clear()
            await telegram_queue.edit(callback.message, "Session killed. Use /start to restart.", parse_mode=None)

        case FlowAction.CANCELLED:
            await state.clear()
            await telegram_queue.edit(callback.message, "Cancelled.", parse_mode=None)


# ===== Launch Helpers =====

async def _launch_claude(message: Message, result: FlowResult, telegram_queue: TelegramQueue):
    """Launch Claude session from message context."""
    from ..launch_animation import launch_with_animation

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, "Project not found", parse_mode=None)
        return

    thread = project.get_or_create_thread(None, "main")

    if thread.launch_task and not thread.launch_task.done():
        await telegram_queue.reply(message, "Launch already in progress", parse_mode=None)
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


async def _launch_claude_from_callback(callback: CallbackQuery, result: FlowResult, telegram_queue: TelegramQueue):
    """Launch Claude session from callback context."""
    from ..launch_animation import launch_with_animation

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


async def _launch_claude_in_thread(message: Message, result: FlowResult, telegram_queue: TelegramQueue):
    """Launch Claude in a specific thread."""
    from ..launch_animation import launch_with_animation

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        return

    thread = project.threads.get(result.thread_id)
    if not thread:
        return

    # Check if tmux already running
    tmux_name = thread.get_tmux_session(project.project_name)
    actual_cwd = thread.worktree_path or project.cwd
    if is_tmux_session_exists(tmux_name):
        # Check if Claude is ready in tmux
        from ..tmux import TmuxSession
        tmux = TmuxSession(tmux_name, actual_cwd)
        if tmux.is_claude_ready():
            await telegram_queue.reply(
                message,
                f"`[v]` Already running\n\nAttach: `tmux attach -t {tmux_name}`"
            )
            return
        else:
            # tmux exists but Claude not ready - kill and restart
            import subprocess
            subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Handle archived topic - reopen it
    if thread.archived:
        thread.archived = False
        project_manager._save()
        # Remove archive icon
        try:
            await message.bot.edit_forum_topic(
                message.chat.id, result.thread_id, icon_custom_emoji_id=""
            )
        except Exception:
            pass  # May fail if no icon was set

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


async def _connect_to_session(message: Message, result: FlowResult, telegram_queue: TelegramQueue):
    """Connect to existing tmux session."""
    project = project_manager.get_by_chat(message.chat.id)
    if project:
        project.tmux_session = result.tmux_session
        project_manager._save()
        await telegram_queue.reply(
            message,
            f"Connected to `{result.tmux_session}`",
        )


async def _connect_to_session_from_callback(callback: CallbackQuery, result: FlowResult):
    """Connect to existing tmux session from callback."""
    project = project_manager.get_by_chat(callback.message.chat.id)
    if project:
        project.tmux_session = result.tmux_session
        project_manager._save()


# ===== Commands =====

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
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

    await _handle_result(message, state, result, telegram_queue)


# ===== FSM State Handlers =====

@router.message(StartFlow.awaiting_project_name)
async def on_project_name(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle project name input."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    thread_id = data.get("thread_id")

    result = start_flow.handle_project_name(message.chat.id, message.text.strip())

    # If thread flow, preserve thread_id in result
    if thread_id and result.thread_id is None:
        result.thread_id = thread_id

    await _handle_result(message, state, result, telegram_queue)


@router.message(StartFlow.awaiting_custom_path)
async def on_custom_path(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle custom path input."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_custom_path(
        message.chat.id,
        data["project"],
        message.text.strip(),
    )

    await _handle_result(message, state, result, telegram_queue)


@router.message(StartFlow.awaiting_clone_url)
async def on_clone_url(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle git clone URL input."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_clone_url(
        message.chat.id,
        data["project"],
        data["path"],
        message.text.strip(),
    )

    await _handle_result(message, state, result, telegram_queue)


# ===== Callback Handlers =====

@router.callback_query(F.data == "start:create_dir")
async def on_create_dir(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle create directory button."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_create_dir(data["project"], data["path"])

    await _handle_callback_result(callback, state, result, telegram_queue)


@router.callback_query(F.data == "start:custom_path")
async def on_custom_path_btn(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle custom path button."""
    await state.set_state(StartFlow.awaiting_custom_path)
    await telegram_queue.edit(callback.message, "Отправь путь к директории:", parse_mode=None)
    await callback.answer()


@router.callback_query(F.data == "start:git_init")
async def on_git_init(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle git init button."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_git_init(
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
        "Видимость репозитория?",
        reply_markup=git_visibility_keyboard(),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data.in_({"start:gh_private", "start:gh_public"}))
async def on_gh_visibility(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle GitHub visibility choice."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    private = callback.data == "start:gh_private"
    result = start_flow.handle_gh_create(
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
    await telegram_queue.edit(callback.message, "Отправь ссылку на репозиторий:", parse_mode=None)
    await callback.answer()


@router.callback_query(F.data == "start:no_git")
async def on_no_git(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle no git button."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_no_git(
        callback.message.chat.id,
        data["project"],
        data["path"],
    )

    await _handle_callback_result(callback, state, result, telegram_queue)


@router.callback_query(F.data == "start:launch_claude")
async def on_launch_claude(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle launch Claude button."""
    data = await state.get_data()

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    await state.clear()
    await telegram_queue.edit(callback.message, "Launching Claude...", parse_mode=None)
    await callback.answer()

    result = FlowResult(
        action=FlowAction.LAUNCH,
        project=data.get("project"),
        path=data.get("path"),
    )
    await _launch_claude_from_callback(callback, result, telegram_queue)


@router.callback_query(F.data == "start:cancel")
async def on_cancel(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle cancel button."""
    await state.clear()
    await telegram_queue.edit(callback.message, "Cancelled.", parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("select_tmux:"))
async def on_tmux_selected(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle tmux selection."""
    start_flow = StartFlowService(project_manager, None)

    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    project_name, tmux_session = parts[1], parts[2]
    result = start_flow.handle_tmux_selected(
        callback.message.chat.id,
        project_name,
        tmux_session,
    )

    await _handle_callback_result(callback, state, result, telegram_queue)


# ===== Restart Flow =====

@router.message(Command("restart"))
async def cmd_restart(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle /restart command."""
    start_flow = StartFlowService(project_manager, None)

    result = start_flow.handle_restart(
        chat_id=message.chat.id,
        thread_id=message.message_thread_id,
    )

    if result.action == FlowAction.ASK_RESTART_CONFIRM:
        await state.set_state(RestartFlow.awaiting_confirm)
        await state.update_data(tmux_session=result.tmux_session)
        await telegram_queue.reply(
            message,
            f"Restart session `{result.tmux_session}`?",
            reply_markup=restart_confirm_keyboard(),
        )
    else:
        await _handle_result(message, state, result, telegram_queue)


@router.callback_query(F.data == "restart:confirm")
async def on_restart_confirm(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle restart confirmation."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    tmux_session = data.get("tmux_session")

    if not tmux_session:
        await callback.answer("Session expired")
        return

    result = start_flow.handle_restart_confirm(tmux_session)

    await _handle_callback_result(callback, state, result, telegram_queue)


@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle restart cancel."""
    start_flow = StartFlowService(project_manager, None)

    result = start_flow.handle_cancel()

    await _handle_callback_result(callback, state, result, telegram_queue)
