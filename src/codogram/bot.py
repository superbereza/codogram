# src/codogram/bot.py
from pathlib import Path
import asyncio

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from .session_manager import project_manager, ProjectState, ThreadInfo
from .tmux import TmuxSession
from .logging_config import logger
from .project_launcher import (
    resolve_project_path,
    is_tmux_session_exists,
    git_clone,
)
from .start_flow import dir_not_found_keyboard
from .tmux_selector import create_tmux_selection_keyboard
from .domain.validators import is_valid_project_name
from .adapters.telegram import send_with_retry

# Conversation state: chat_id -> {"state": str, "project": str, "path": str, ...}
_start_state: dict[int, dict] = {}

router = Router()

async def require_forum_group(message: Message) -> bool:
    """Check if message is from a forum group. Returns False and sends error if not."""
    if message.chat.type == "private":
        await message.answer("`[!]` This command requires a group with topics.", parse_mode="Markdown")
        return False
    if not message.chat.is_forum:
        await message.answer("`[!]` Topics required. Enable in group settings -> Topics", parse_mode="Markdown")
        return False
    return True

def get_session_for_chat(chat_id: int) -> TmuxSession | None:
    """Get TmuxSession for chat_id (main thread)."""
    project = project_manager.get_by_chat(chat_id)
    if not project or not project.cwd:
        return None

    # Try threads[None] first (unified path)
    thread = project.threads.get(None)
    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        return TmuxSession(tmux_name, project.cwd)

    # Legacy fallback
    if project.tmux_session:
        return TmuxSession(project.tmux_session, project.cwd)

    return None

def get_project_for_chat(chat_id: int) -> tuple[str | None, ProjectState | None]:
    """Get project name and state for chat.

    Returns:
        (project_name, project_state) - project_state may be None if not yet created
    """
    # Check if chat already has a project
    project = project_manager.get_by_chat(chat_id)
    if project:
        return project.project_name, project

    # No project found for this chat
    return None, None

def is_claude_running(project: ProjectState) -> bool:
    """Check if Claude is fully running for project.

    Returns True if:
    - tmux session exists
    - poller_task is running
    - watcher_task is running (session discovered)
    """
    if not project or not project.tmux_session:
        return False

    if not is_tmux_session_exists(project.tmux_session):
        return False

    if not project.poller_task or project.poller_task.done():
        return False

    if not project.watcher_task or project.watcher_task.done():
        return False

    return True

async def show_status(message: Message, project: ProjectState):
    """Show status of active Claude session."""
    status_lines = [
        f"**Claude active**",
        f"",
        f"Project: `{project.project_name}`",
        f"Path: `{project.cwd}`",
        f"Tmux: `{project.tmux_session}`",
    ]

    if project.session_id:
        status_lines.append(f"Session: `{project.session_id[:8]}...`")

    status_lines.extend([
        "",
        f"Attach: `tmux attach -t {project.tmux_session}`",
    ])

    await message.answer("\n".join(status_lines), parse_mode="Markdown")

def _make_task_starters(bot):
    """Create task starter functions with bot and queue bound.

    Returns:
        (start_poller, start_watcher) - async functions to start tasks
    """
    from . import main

    async def start_poller(p: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p, main.telegram_queue)

    async def start_watcher(p: ProjectState, send_missed: bool = False) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p, main.telegram_queue, send_missed)

    return start_poller, start_watcher

async def _start_project_flow(message: Message, project: ProjectState):
    """Main flow: resolve path → check exists → launch or ask."""
    chat_id = message.chat.id
    project.chat_id = chat_id

    # Resolve path: saved cwd or convention ~/dev/{project_name}
    if project.cwd:
        path = project.cwd
        exists = Path(path).is_dir()
    else:
        path_result = resolve_project_path(project.project_name, None)
        path = path_result.path
        exists = path_result.exists

    if exists:
        # Directory exists - discover tmux and launch/connect
        project.cwd = path
        await _connect_or_launch(message, project)
    else:
        # Directory doesn't exist - ask what to do
        _start_state[chat_id] = {
            "state": "awaiting_dir_choice",
            "project": project.project_name,
            "path": path,
        }
        await message.answer(
            f"Directory `{path}` not found.\n\nWhat to do?",
            reply_markup=dir_not_found_keyboard(),
            parse_mode="Markdown",
        )

    project_manager._save()


async def _start_thread_flow(message: Message, project: ProjectState, thread: ThreadInfo):
    """Handle /start in an existing thread - check tmux and connect or launch."""
    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)

    if tmux.exists():
        # Thread's tmux exists - show status
        await message.answer(
            f"Claude active in `{tmux_name}`\n\n"
            f"Attach: `tmux attach -t {tmux_name}`",
            parse_mode="Markdown",
        )
    else:
        # No tmux - launch Claude for this thread
        start_poller, start_watcher = _make_task_starters(message.bot)
        await launch_claude_in_thread(message, project, thread, start_poller, start_watcher)
        project_manager._save()


async def _connect_or_launch(message: Message, project: ProjectState):
    """Connect to existing tmux or offer to launch new Claude session."""
    chat_id = message.chat.id
    cwd = project.cwd

    # Discover tmux
    from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention
    tmux_list = find_all_tmux_by_cwd(cwd)

    if len(tmux_list) == 0:
        # No tmux found - check by convention
        tmux_by_convention = find_tmux_by_convention(project.project_name)
        if tmux_by_convention:
            project.tmux_session = tmux_by_convention
            await message.answer(f"Connected to tmux: {tmux_by_convention}")
        else:
            # No tmux at all - offer to create
            _start_state[chat_id] = {
                "state": "awaiting_launch_confirm",
                "project": project.project_name,
                "path": cwd,
            }
            await message.answer(
                f"Claude not running in `{cwd}`.\n\nLaunch?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Yes, launch", callback_data="start:launch_claude"),
                        InlineKeyboardButton(text="No", callback_data="start:cancel"),
                    ]
                ]),
                parse_mode="Markdown",
            )
            return
    elif len(tmux_list) == 1:
        project.tmux_session = tmux_list[0]
        await message.answer(f"Connected to tmux: {tmux_list[0]}")
    else:
        # Multiple - let user choose
        keyboard = create_tmux_selection_keyboard(tmux_list, project.project_name)
        await message.answer(
            f"Multiple tmux sessions found:\n\nSelect:",
            reply_markup=keyboard
        )
        project_manager._save()
        return

    # Discover session and start tasks
    project_manager.refresh_project_session(project)

    start_poller, start_watcher = _make_task_starters(message.bot)
    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()

    await send_with_retry(
        message.bot,
        message.chat.id,
        f"Claude running in `{project.tmux_session}`\n\n"
        f"Attach: `tmux attach -t {project.tmux_session}`",
    )


async def launch_claude_in_thread(
    message: Message,
    project: ProjectState,
    thread: ThreadInfo,
    start_poller,
    start_watcher,
) -> bool:
    """Launch Claude for a specific thread (topic).

    Returns True if successful, False otherwise.
    Uses background launch with animation.
    """
    # Race protection: check if launch already in progress
    if thread.launch_task and not thread.launch_task.done():
        await message.answer("Launch already in progress...")
        return False

    from .launch_animation import launch_with_animation
    from .main import telegram_queue

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=message.bot,
            chat_id=message.chat.id,
            thread_id=thread.thread_id,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )

    project_manager._save()
    return True


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    """Handle generic cancel button."""
    chat_id = callback.message.chat.id
    _start_state.pop(chat_id, None)
    await callback.message.edit_text("Cancelled.")
    await callback.answer()


async def _do_branch_cleanup(message: Message, project: ProjectState, thread: ThreadInfo, force: bool):
    """Clean up worktree, tmux, and archive topic."""
    import subprocess
    from .worktree import remove_worktree

    main_repo = Path(project.cwd)
    worktree_path = Path(thread.worktree_path) if thread.worktree_path else None
    branch_name = thread.name

    # Cancel background tasks
    if thread.watcher_task:
        thread.watcher_task.cancel()
    if thread.poller_task:
        thread.poller_task.cancel()
    if thread.binding_task:
        thread.binding_task.cancel()

    # Kill tmux
    tmux_name = thread.get_tmux_session(project.project_name)
    subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Remove worktree and branch
    if worktree_path:
        remove_worktree(main_repo, worktree_path, branch_name, delete_branch=True, force=force)

    # Archive topic
    try:
        await message.bot.close_forum_topic(message.chat.id, thread.thread_id)
        await message.bot.edit_forum_topic(message.chat.id, thread.thread_id, icon_custom_emoji_id="5357315181649076022")  # archive folder icon
    except Exception:
        pass  # Topic may already be closed

    # Update thread state
    thread.archived = True
    thread.worktree_path = None
    thread.session_id = None
    project_manager._save()


async def _do_branch_create(message: Message, project: ProjectState, branch_name: str, base_branch: str):
    """Create topic + worktree + launch Claude using unified service."""
    from .services.launch import create_thread_with_session

    # Unified flow: topic created first, then worktree, then Claude
    # All status messages go to the new topic
    thread = await create_thread_with_session(
        bot=message.bot,
        chat_id=message.chat.id,
        project=project,
        name=branch_name,
        create_worktree=True,
        base_branch=base_branch,
    )

    if not thread:
        # Error already reported in the topic by the service
        await message.answer("`[x]` Branch creation failed. Check the new topic for details.", parse_mode="Markdown")


@router.message()
async def on_message(message: Message):
    """Handle regular messages."""
    # Log incoming message
    text_preview = message.text[:100] if message.text else '<no text>'
    thread_id = message.message_thread_id
    logger.info(f"Incoming message from user={message.from_user.id} chat={message.chat.id} thread={thread_id}: {text_preview}")

    if not message.text:
        return

    chat_id = message.chat.id
    # thread_id already logged above

    # Skip commands
    if message.text.startswith("/"):
        return

    # Check if we're in conversation flow
    state = _start_state.get(chat_id)
    if state:
        if state["state"] == "awaiting_project_name":
            # User sent project name
            project_name = message.text.strip()
            if not project_name or not is_valid_project_name(project_name):
                await message.answer(
                    "Project name can only contain letters, digits, `-` and `_`.",
                    parse_mode="Markdown",
                )
                return
            if len(project_name) > 35:
                await message.answer(
                    "`[!]` Project name too long (max 35 chars). "
                    "Rename group or use /register_dir with shorter name.",
                    parse_mode="Markdown",
                )
                return

            project = project_manager.get_or_create(project_name)
            project.chat_id = chat_id

            _start_state.pop(chat_id, None)
            await _start_project_flow(message, project)
            return

        elif state["state"] == "awaiting_custom_path":
            # User sent custom path
            path = message.text.strip()
            if not Path(path).expanduser().is_dir():
                await message.answer(f"Directory `{path}` does not exist.", parse_mode="Markdown")
                return

            # Get or create project and save path
            project = project_manager.get_or_create(state["project"])
            project.chat_id = chat_id
            project.cwd = str(Path(path).expanduser())

            # Use background launch with animation
            thread = project.get_or_create_thread(None, "main")
            _start_state.pop(chat_id, None)

            if not (thread.launch_task and not thread.launch_task.done()):
                from .launch_animation import launch_with_animation
                from .main import telegram_queue

                thread.launch_task = asyncio.create_task(
                    launch_with_animation(
                        bot=message.bot,
                        chat_id=chat_id,
                        thread_id=None,
                        project=project,
                        thread=thread,
                        queue=telegram_queue,
                    )
                )
                project_manager._save()
            return

        elif state["state"] == "awaiting_clone_url":
            # User sent clone URL
            url = message.text.strip()
            await message.answer("Cloning repository...")

            result = git_clone(state["path"], url)
            if not result.success:
                await message.answer(f"Clone error: {result.error}")
                return

            # Get or create project
            project = project_manager.get_or_create(state["project"])
            project.cwd = state["path"]

            # Use background launch with animation
            thread = project.get_or_create_thread(None, "main")
            _start_state.pop(chat_id, None)

            if not (thread.launch_task and not thread.launch_task.done()):
                from .launch_animation import launch_with_animation
                from .main import telegram_queue

                thread.launch_task = asyncio.create_task(
                    launch_with_animation(
                        bot=message.bot,
                        chat_id=chat_id,
                        thread_id=None,
                        project=project,
                        thread=thread,
                        queue=telegram_queue,
                    )
                )
                project_manager._save()
            return

    # Normal message - route through threads (unified path)
    project = project_manager.get_by_chat(chat_id)
    if not project:
        return

    # Get or create thread for this topic
    thread = project.threads.get(thread_id)
    logger.debug(f"Message routing: project={project.project_name} thread_id={thread_id} thread={thread}")

    if thread_id is not None and not thread:
        # Unknown topic - create pending ThreadInfo, show hint once
        thread = ThreadInfo(thread_id=thread_id, name="pending")
        project.threads[thread_id] = thread
        project_manager._save()
        await message.answer("Use /start or /thread_create to connect Claude to this topic")
        return

    # For thread_id=None (General/Private/Simple), auto-create "main" thread if missing
    if thread_id is None and not thread:
        thread = project.get_or_create_thread(None, "main")
        project_manager._save()

    # Skip pending threads (no tmux yet)
    if thread and thread.name == "pending":
        return

    # All messages now go through thread path
    start_poller, start_watcher = _make_task_starters(message.bot)

    if thread.session_id is None:
        # No session bound - use session binding (match by user message)
        from .history_watcher import poll_for_session_thread
        from . import main

        thread.last_sent_message = message.text

        # Start binding task if not already running
        if not thread.binding_task or thread.binding_task.done():
            logger.debug(f"Starting binding task for thread {thread.name}")
            thread.binding_task = asyncio.create_task(
                poll_for_session_thread(project, thread, message.bot, start_poller, start_watcher, main.telegram_queue)
            )
        else:
            logger.debug(f"Binding task already running for thread {thread.name}")
    else:
        # Session already bound - session changes now handled by:
        # - /new, /clear Telegram commands (set awaiting_new_session)
        # - HistoryWatcher (binds new sessions to awaiting threads)
        # See: docs/designs/2025-12-29-session-binder-design.md
        pass

    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)

    logger.debug(f"tmux_send: project={project.project_name} tmux={tmux_name}")

    if tmux.exists():
        tmux.send(message.text)
        logger.debug(f"sent_to_tmux: {message.text[:50]}")
    else:
        # No active session - only respond in group chats
        logger.warning(f"no_tmux_session: project={project.project_name}")
        if message.chat.id < 0:  # Negative IDs are groups/channels
            await message.answer("No active Claude session. Use /start to launch.")
