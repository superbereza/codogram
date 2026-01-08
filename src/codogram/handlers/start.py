"""Start flow handlers - /start, /restart and related callbacks."""
import asyncio

from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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
from ..services.menu import register_menu_for_chat

router = Router(name="start")


async def _register_chat_menu(bot: Bot, chat) -> None:
    """Register scope-based menu for chat.

    Helper to avoid repeating registration logic in 4 entry points.
    Called when project becomes active (connect or launch).
    """
    await register_menu_for_chat(bot, chat.id, is_forum=chat.is_forum or False)


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
            await _register_chat_menu(message.bot, message.chat)
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
            await _register_chat_menu(message.bot, message.chat)
            await telegram_queue.reply(
                message,
                f"`[v]` Thread `{result.thread_name}` running\n\nAttach: `tmux attach -t {result.tmux_session}`",
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

    await _register_chat_menu(message.bot, message.chat)
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

    await _register_chat_menu(callback.bot, callback.message.chat)
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

    # Always try to reopen topic and reset icon
    if result.thread_id:
        from ..logging_config import logger
        was_reopened = False

        # Try to reopen (may fail if already open - that's fine)
        try:
            await message.bot.reopen_forum_topic(message.chat.id, result.thread_id)
            logger.info(f"Topic {result.thread_id} reopened")
            was_reopened = True
        except Exception:
            pass  # Topic already open

        # Reset icon to ballot box 🗳️ when topic is reopened
        if was_reopened:
            try:
                # 🗳️ icon - empty string doesn't work in Telegram API
                await message.bot.edit_forum_topic(
                    message.chat.id, result.thread_id,
                    icon_custom_emoji_id="5350387571199319521"
                )
                logger.info(f"Topic {result.thread_id} icon set to 🗳️")
            except Exception as e:
                logger.warning(f"Failed to set topic icon: {e}")

        # Clear archived flag if it was set
        if thread.archived:
            thread.archived = False
            project_manager._save()

    if thread.launch_task and not thread.launch_task.done():
        return

    # Determine cwd (worktree or project)
    cwd = thread.worktree_path if thread.has_valid_worktree() else None

    # Check for session resume
    session_id = None
    if thread.has_valid_session():
        session_id = thread.session_id
    elif thread.session_id and not thread.has_valid_session():
        # Session ID exists but jsonl missing - show error
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Start new session",
                callback_data=f"resume:start_new:{result.thread_id}"
            )],
            [InlineKeyboardButton(text="Cancel", callback_data=f"resume:cancel:{result.thread_id}")]
        ])
        await telegram_queue.reply(
            message,
            "`[!]` Previous session not found",
            reply_markup=keyboard,
        )
        return

    # Check worktree exists for branch topics
    if thread.worktree_path and not thread.has_valid_worktree():
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Recreate worktree",
                callback_data=f"resume:recreate:{result.thread_id}"
            )],
            [InlineKeyboardButton(text="Cancel", callback_data=f"resume:cancel:{result.thread_id}")]
        ])
        await telegram_queue.reply(
            message,
            f"`[!]` Worktree not found: `{thread.worktree_path}`",
            reply_markup=keyboard,
        )
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=message.bot,
            chat_id=message.chat.id,
            thread_id=result.thread_id,
            project=project,
            thread=thread,
            queue=telegram_queue,
            session_id=session_id,  # Pass session_id for resume
            cwd=cwd,                # Pass worktree cwd for branches
        )
    )


async def _connect_to_session(message: Message, result: FlowResult, telegram_queue: TelegramQueue):
    """Connect to existing tmux session."""
    project = project_manager.get_by_chat(message.chat.id)
    if project:
        project.tmux_session = result.tmux_session
        project_manager._save()
        await _register_chat_menu(message.bot, message.chat)
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
        await _register_chat_menu(callback.bot, callback.message.chat)


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

    # Cancel background tasks before killing tmux
    project = project_manager.get_by_chat(callback.message.chat.id)
    if project:
        thread = project.get_thread(callback.message.message_thread_id)
        if thread:
            for task in [thread.launch_task, thread.watcher_task, thread.poller_task, thread.binding_task]:
                if task and not task.done():
                    task.cancel()

    result = start_flow.handle_restart_confirm(tmux_session)

    await _handle_callback_result(callback, state, result, telegram_queue)


@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle restart cancel."""
    start_flow = StartFlowService(project_manager, None)

    result = start_flow.handle_cancel()

    await _handle_callback_result(callback, state, result, telegram_queue)


# ===== Resume Error Recovery =====

@router.callback_query(F.data.startswith("resume:"))
async def on_resume_callback(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle resume error recovery callbacks."""
    parts = callback.data.split(":")
    action = parts[1]
    thread_id = int(parts[2]) if parts[2] != "None" else None

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(thread_id)

    if action == "start_new":
        # Clear stale session and start fresh
        if thread:
            thread.session_id = None
            thread.jsonl_path = None
            project_manager._save()

        await telegram_queue.edit(callback.message, "`[~]` Starting new session...")
        await callback.answer()

        # Trigger launch
        from ..launch_animation import launch_with_animation
        cwd = thread.worktree_path if thread and thread.has_valid_worktree() else None

        if thread:
            thread.launch_task = asyncio.create_task(
                launch_with_animation(
                    bot=callback.bot,
                    chat_id=callback.message.chat.id,
                    thread_id=thread_id,
                    project=project,
                    thread=thread,
                    queue=telegram_queue,
                    cwd=cwd,
                )
            )

    elif action == "recreate":
        # Recreate worktree from existing branch
        if not thread:
            await callback.answer("Thread not found")
            return

        await telegram_queue.edit(callback.message, "`[~]` Recreating worktree...")
        await callback.answer()

        # Attach worktree to existing branch
        from pathlib import Path
        import subprocess

        main_repo = Path(project.cwd)
        branch_name = thread.name
        worktree_path = main_repo / ".worktrees" / branch_name

        try:
            # Ensure .worktrees/ directory exists
            worktree_path.parent.mkdir(parents=True, exist_ok=True)

            # git worktree add <path> <existing-branch>
            # Use asyncio.to_thread to avoid blocking event loop
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "worktree", "add", str(worktree_path), branch_name],
                cwd=str(main_repo),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())

            thread.worktree_path = str(worktree_path)
            project_manager._save()

            await telegram_queue.edit(callback.message, "`[v]` Worktree recreated. Use /start to launch.")
        except Exception as e:
            await telegram_queue.edit(callback.message, f"`[x]` Failed to recreate: {e}")

    elif action == "cancel":
        await telegram_queue.edit(callback.message, "Cancelled.")
        await callback.answer()
