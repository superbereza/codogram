# src/codogram/bot.py
from pathlib import Path
import asyncio
import re
import time

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.exceptions import TelegramRetryAfter

from .config import settings
from .session_manager import project_manager, ProjectState, ThreadInfo
from .tmux import TmuxSession
from .state import permission_messages
from .logging_config import logger
from .project_launcher import (
    resolve_project_path,
    is_tmux_session_exists,
    create_project_directory,
    git_init,
    git_init_with_github,
    git_clone,
)
from .start_flow import (
    dir_not_found_keyboard,
    git_setup_keyboard,
    git_visibility_keyboard,
    restart_confirm_keyboard,
)
from .tmux_selector import create_tmux_selection_keyboard

# Conversation state: chat_id -> {"state": str, "project": str, "path": str, ...}
_start_state: dict[int, dict] = {}

router = Router()

# Cache admin IDs
_admin_ids: set[int] | None = None

def get_admin_ids() -> set[int]:
    """Get admin IDs (cached)."""
    global _admin_ids
    if _admin_ids is None:
        _admin_ids = settings.get_admin_ids()
    return _admin_ids

def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id in get_admin_ids()

def is_valid_project_name(name: str) -> bool:
    """Check if project name is valid.

    Valid names contain only: letters, digits, dash, underscore.
    """
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))


async def require_forum_group(message: Message) -> bool:
    """Check if message is from a forum group. Returns False and sends error if not."""
    if message.chat.type == "private":
        await message.answer("`[!]` This command requires a group with topics.", parse_mode="MarkdownV2")
        return False
    if not message.chat.is_forum:
        await message.answer("`[!]` Topics required. Enable in group settings -> Topics", parse_mode="MarkdownV2")
        return False
    return True


async def send_with_retry(
    message: Message,
    text: str,
    parse_mode: str = "Markdown",
    retries: int = 3,
    message_thread_id: int | None = None,
) -> bool:
    """Send message with retry on rate limit."""
    for attempt in range(retries):
        try:
            if message_thread_id is not None:
                await message.bot.send_message(
                    message.chat.id,
                    text,
                    parse_mode=parse_mode,
                    message_thread_id=message_thread_id,
                )
            else:
                await message.answer(text, parse_mode=parse_mode)
            return True
        except TelegramRetryAfter as e:
            logger.warning(f"Rate limited, retrying in {e.retry_after}s (attempt {attempt + 1}/{retries})")
            await asyncio.sleep(e.retry_after + 1)
    logger.error("Failed to send message after retries")
    return False


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

    await message.answer("\n".join(status_lines), parse_mode="MarkdownV2")

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
            parse_mode="MarkdownV2",
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
            parse_mode="MarkdownV2",
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
                parse_mode="MarkdownV2",
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
        message,
        f"Claude running in `{project.tmux_session}`\n\n"
        f"Attach: `tmux attach -t {project.tmux_session}`",
    )


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Start command - auto-detect project or show status.

    Usage:
        /start              - auto-detect from chat or ask for project name
        /start <project>    - start with specific project
    """
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id
    args = message.text.split()[1:]  # Skip /start

    logger.info(f"cmd_start: chat_id={chat_id} thread_id={thread_id} args={args}")

    # If in a topic, use thread-specific flow
    if thread_id is not None:
        project = project_manager.get_by_chat(chat_id)
        logger.debug(f"cmd_start: topic mode, project={project.project_name if project else None}")
        if project:
            thread = project.threads.get(thread_id)
            logger.debug(f"cmd_start: thread={thread}")
            if thread:
                if thread.name == "pending":
                    # Upgrade pending thread
                    from .magic_names import get_random_magic_name
                    existing_names = {t.name for t in project.threads.values() if t.name != "pending"}
                    thread.name = get_random_magic_name(existing_names)

                    start_poller, start_watcher = _make_task_starters(message.bot)
                    await launch_claude_in_thread(message, project, thread, start_poller, start_watcher)
                    project_manager._save()
                else:
                    # Existing thread - check tmux and connect or launch
                    await _start_thread_flow(message, project, thread)
                return
            else:
                # Topic not registered - register and launch
                from .magic_names import get_random_magic_name
                existing_names = {t.name for t in project.threads.values() if t.name != "pending"}
                thread_name = get_random_magic_name(existing_names)

                thread = ThreadInfo(thread_id=thread_id, name=thread_name)
                project.threads[thread_id] = thread

                start_poller, start_watcher = _make_task_starters(message.bot)
                await launch_claude_in_thread(message, project, thread, start_poller, start_watcher)
                project_manager._save()
                return

    # Case 1: Project name provided
    if args:
        project_name = args[0]
        if not is_valid_project_name(project_name):
            await message.answer(
                "Project name can only contain letters, digits, `-` and `_`.",
                parse_mode="MarkdownV2",
            )
            return
        if len(project_name) > 35:
            await message.answer(
                "`[!]` Project name too long (max 35 chars). "
                "Rename group or use /register_dir with shorter name.",
                parse_mode="MarkdownV2",
            )
            return
        project = project_manager.get_or_create(project_name)
        project.chat_id = chat_id
        await _start_project_flow(message, project)
        return

    # Case 2: No args - auto-detect from chat
    project_name, project = get_project_for_chat(chat_id)

    if project and is_claude_running(project):
        await show_status(message, project)
        return

    if project:
        if project.cwd and Path(project.cwd).is_dir():
            # cwd exists - use thread flow (respects naming convention)
            thread = project.get_or_create_thread(None, "main")
            await _start_thread_flow(message, project, thread)
            project_manager._save()
        else:
            # cwd doesn't exist - need setup
            await _start_project_flow(message, project)
        return

    # Case 3: New chat - use chat title as project name
    chat_title = message.chat.title
    if chat_title:
        # Sanitize title to valid project name (replace spaces with -, remove invalid chars)
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', chat_title)
        sanitized = re.sub(r'-+', '-', sanitized).strip('-')  # Collapse multiple dashes
        if sanitized and is_valid_project_name(sanitized):
            if len(sanitized) > 35:
                await message.answer(
                    "`[!]` Project name too long (max 35 chars). "
                    "Rename group or use /register_dir with shorter name.",
                    parse_mode="MarkdownV2",
                )
                return
            project = project_manager.get_or_create(sanitized)
            project.chat_id = chat_id
            await _start_project_flow(message, project)
            return

    # Fallback: ask for project name (private chat or invalid title)
    _start_state[chat_id] = {"state": "awaiting_project_name"}
    await message.answer(
        "Send project name (e.g. `my-project`):",
        parse_mode="MarkdownV2",
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


@router.message(Command("thread_delete"))
async def cmd_thread_delete(message: Message):
    """Close current thread and its Claude session."""
    if not is_admin(message.from_user.id):
        return

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
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

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
    import subprocess
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


@router.message(Command("thread_create"))
async def cmd_thread_create(message: Message):
    """Create a new thread (topic) with its own Claude session."""
    if not is_admin(message.from_user.id):
        return

    if not await require_forum_group(message):
        return

    chat_id = message.chat.id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("Project not found. Use /start first")
        return

    # Parse optional name from command
    from .magic_names import get_random_magic_name
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        name = args[1].strip().lower()
        # Validate name
        if not name.replace("-", "").replace("_", "").isalnum():
            await message.answer("Name can only contain letters, digits, - and _")
            return
    else:
        # Get existing thread names to exclude
        existing_names = {t.name for t in project.threads.values() if t.name != "pending"}
        name = get_random_magic_name(existing_names)

    # Check if name already exists
    for thread in project.threads.values():
        if thread.name == name:
            await message.answer(f"Thread with name '{name}' already exists")
            return

    # Check for non-worktree threads and warn user about /branch_create
    non_worktree_threads = [
        t for t in project.threads.values()
        if t.thread_id is not None and t.worktree_path is None and not t.archived
    ]

    if non_worktree_threads:
        # Store pending thread name for confirmation
        _start_state[chat_id] = {
            "state": "thread_create_pending",
            "name": name,
        }
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create new git worktree", callback_data="branch_create_redirect")],
            [InlineKeyboardButton(text="Create in main anyway", callback_data="thread_create_confirm")],
            [InlineKeyboardButton(text="[x] Cancel", callback_data="cancel")]
        ])
        await message.answer(
            "You already have a topic working in the main directory.\n\n"
            "Creating another one means both Claude sessions will edit the same files, "
            "which may cause conflicts.\n\n"
            "*Recommendation:* use git worktree — each topic gets "
            "an isolated copy of the repository.",
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )
        return

    # Use launch service to create topic + ThreadInfo + launch Claude
    from .services.launch import create_thread_with_session

    thread = await create_thread_with_session(
        bot=message.bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )

    if not thread:
        await message.answer("Error creating topic")
        return


@router.callback_query(F.data == "start:create_dir")
async def on_start_create_dir(callback: CallbackQuery):
    """Handle create directory button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Session expired, start again with /start")
        return

    # Create directory
    result = create_project_directory(state["path"])
    if not result.success:
        await callback.message.edit_text(f"Error creating directory: {result.error}")
        await callback.answer()
        return

    # Ask about git
    state["state"] = "awaiting_git_choice"
    await callback.message.edit_text(
        f"Directory `{state['path']}` created.\n\n"
        f"**Setup git?**\n\n"
        f"• `git init` — local repository\n"
        f"• `git init + gh repo create` — create on GitHub\n"
        f"• `git clone` — clone existing\n"
        f"• No git — empty folder",
        reply_markup=git_setup_keyboard(),
        parse_mode="MarkdownV2",
    )
    await callback.answer()


@router.callback_query(F.data == "start:custom_path")
async def on_start_custom_path(callback: CallbackQuery):
    """Handle custom path button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Session expired")
        return

    state["state"] = "awaiting_custom_path"
    await callback.message.edit_text("Send project directory path:")
    await callback.answer()


@router.callback_query(F.data == "start:git_init")
async def on_start_git_init(callback: CallbackQuery):
    """Handle git init button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Session expired")
        return

    result = git_init(state["path"])
    if not result.success:
        await callback.message.edit_text(f"Error git init: {result.error}")
    else:
        await callback.message.edit_text("Git initialized. Launching Claude...")

        # Get or create project
        project = project_manager.get_or_create(state["project"])
        project.cwd = state["path"]

        # Use background launch with animation
        thread = project.get_or_create_thread(None, "main")
        if not (thread.launch_task and not thread.launch_task.done()):
            from .launch_animation import launch_with_animation
            from .main import telegram_queue

            thread.launch_task = asyncio.create_task(
                launch_with_animation(
                    bot=callback.bot,
                    chat_id=chat_id,
                    thread_id=None,
                    project=project,
                    thread=thread,
                    queue=telegram_queue,
                )
            )
            project_manager._save()

    _start_state.pop(chat_id, None)
    await callback.answer()


@router.callback_query(F.data == "start:git_gh")
async def on_start_git_gh(callback: CallbackQuery):
    """Handle git + gh button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Session expired")
        return

    state["state"] = "awaiting_gh_visibility"
    await callback.message.edit_text(
        "Repository visibility?",
        reply_markup=git_visibility_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"start:gh_private", "start:gh_public"}))
async def on_start_gh_visibility(callback: CallbackQuery):
    """Handle GitHub visibility choice."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Session expired")
        return

    private = callback.data == "start:gh_private"
    await callback.message.edit_text("Creating GitHub repository...")

    result = git_init_with_github(state["path"], private=private)
    if not result.success:
        await callback.message.edit_text(f"Error: {result.error}")
    else:
        await callback.message.edit_text("Repository created. Launching Claude...")

        # Get or create project
        project = project_manager.get_or_create(state["project"])
        project.cwd = state["path"]

        # Use background launch with animation
        thread = project.get_or_create_thread(None, "main")
        if not (thread.launch_task and not thread.launch_task.done()):
            from .launch_animation import launch_with_animation
            from .main import telegram_queue

            thread.launch_task = asyncio.create_task(
                launch_with_animation(
                    bot=callback.bot,
                    chat_id=chat_id,
                    thread_id=None,
                    project=project,
                    thread=thread,
                    queue=telegram_queue,
                )
            )
            project_manager._save()

    _start_state.pop(chat_id, None)
    await callback.answer()


@router.callback_query(F.data == "start:git_clone")
async def on_start_git_clone(callback: CallbackQuery):
    """Handle git clone button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Session expired")
        return

    state["state"] = "awaiting_clone_url"
    await callback.message.edit_text(
        "Send repository URL:\n"
        "• SSH: `git@github.com:user/repo.git`\n"
        "• HTTPS: `https://github.com/user/repo.git`",
        parse_mode="MarkdownV2",
    )
    await callback.answer()


@router.callback_query(F.data == "start:no_git")
async def on_start_no_git(callback: CallbackQuery):
    """Handle no git button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Session expired")
        return

    await callback.message.edit_text("Launching Claude...")

    # Get or create project
    project = project_manager.get_or_create(state["project"])
    project.cwd = state["path"]

    # Use background launch with animation
    thread = project.get_or_create_thread(None, "main")
    if not (thread.launch_task and not thread.launch_task.done()):
        from .launch_animation import launch_with_animation
        from .main import telegram_queue

        thread.launch_task = asyncio.create_task(
            launch_with_animation(
                bot=callback.bot,
                chat_id=chat_id,
                thread_id=None,
                project=project,
                thread=thread,
                queue=telegram_queue,
            )
        )
        project_manager._save()

    _start_state.pop(chat_id, None)
    await callback.answer()


@router.message(Command("branch_create"))
async def cmd_branch_create(message: Message):
    """Create a new worktree branch with isolated Claude session."""
    if not is_admin(message.from_user.id):
        return

    if not await require_forum_group(message):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("`[!]` Project not registered. Use /start first.", parse_mode="MarkdownV2")
        return

    # Check git repo
    from .git_utils import is_git_repo
    if not is_git_repo(Path(project.cwd)):
        await message.answer("`[x]` Git repository required for /branch_create", parse_mode="MarkdownV2")
        return

    # Parse name argument
    args = message.text.split(maxsplit=1)
    branch_name = args[1] if len(args) > 1 else None

    # Generate magic name if not provided
    if not branch_name:
        from .magic_names import get_random_magic_name
        existing_names = {t.name for t in project.threads.values()}
        branch_name = get_random_magic_name(existing_names)

    # Sanitize branch name
    from .git_utils import sanitize_branch_name, max_branch_name_length, has_uncommitted_changes, get_default_branch
    branch_name = sanitize_branch_name(branch_name)

    # Check length
    max_len = max_branch_name_length(project.project_name)
    if len(branch_name) > max_len:
        await message.answer(f"`[x]` Name too long (max {max_len} chars for this project)", parse_mode="MarkdownV2")
        return

    # Get default branch
    default_branch = get_default_branch(Path(project.cwd))

    # Check if creating from worktree topic or main
    current_thread = project.threads.get(message.message_thread_id)
    if current_thread and current_thread.worktree_path:
        # From worktree topic - show base branch selection
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"From {default_branch}", callback_data=f"bc_base:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text=f"From {current_thread.name}", callback_data=f"bc_base:{branch_name}:{current_thread.name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await message.answer("Create branch from:", reply_markup=keyboard)
        return

    # From main - check uncommitted changes
    if has_uncommitted_changes(Path(project.cwd)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create clean (from last commit)", callback_data=f"bc_create:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text="Commit first", callback_data=f"bc_commit:{branch_name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await message.answer("`[!]` Uncommitted changes detected", reply_markup=keyboard, parse_mode="MarkdownV2")
        return

    # No uncommitted changes - create directly
    await _do_branch_create(message, project, branch_name, default_branch)


@router.callback_query(F.data.startswith("bc_base:"))
async def cb_branch_create_base(callback: CallbackQuery):
    """Handle base branch selection for branch_create."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    _, branch_name, base_branch = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    # Check uncommitted in selected base
    from .git_utils import has_uncommitted_changes, get_default_branch
    base_path = project.cwd
    if base_branch != get_default_branch(Path(project.cwd)):
        # Find worktree path for this branch
        for t in project.threads.values():
            if t.name == base_branch and t.worktree_path:
                base_path = t.worktree_path
                break

    if has_uncommitted_changes(Path(base_path)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create from last commit", callback_data=f"bc_create:{branch_name}:{base_branch}")],
            [InlineKeyboardButton(text="Commit first", callback_data=f"bc_commit:{branch_name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await callback.message.edit_text(f"`[!]` Uncommitted changes in {base_branch}", reply_markup=keyboard, parse_mode="MarkdownV2")
        return

    await callback.message.delete()
    await _do_branch_create(callback.message, project, branch_name, base_branch)
    await callback.answer()


@router.callback_query(F.data.startswith("bc_create:"))
async def cb_branch_create_do(callback: CallbackQuery):
    """Create branch from last commit."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    _, branch_name, base_branch = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    await callback.message.delete()
    await _do_branch_create(callback.message, project, branch_name, base_branch)
    await callback.answer()


@router.callback_query(F.data.startswith("bc_commit:"))
async def cb_branch_create_commit(callback: CallbackQuery):
    """Send commit request to Claude."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    _, branch_name = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(callback.message.message_thread_id)

    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        tmux = TmuxSession(tmux_name, project.cwd)
        if tmux.exists():
            tmux.send("Commit current changes in logical chunks with descriptive messages.")

    await callback.message.edit_text(
        "`[~]` Sent: \"Commit current changes in logical chunks with descriptive messages.\"\n\n"
        f"Run `/branch_create {branch_name}` again after commit.",
        parse_mode="MarkdownV2"
    )
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    """Handle generic cancel button."""
    chat_id = callback.message.chat.id
    _start_state.pop(chat_id, None)
    await callback.message.edit_text("Cancelled.")
    await callback.answer()


@router.callback_query(F.data == "thread_create_confirm")
async def cb_thread_create_confirm(callback: CallbackQuery):
    """Handle thread_create confirmation (create in main anyway)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)

    if not state or state.get("state") != "thread_create_pending":
        await callback.answer("Session expired")
        return

    name = state.get("name")
    _start_state.pop(chat_id, None)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    await callback.message.delete()

    # Use launch service to create topic + ThreadInfo + launch Claude
    from .services.launch import create_thread_with_session

    thread = await create_thread_with_session(
        bot=callback.bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )

    if not thread:
        await callback.bot.send_message(chat_id, "Error creating topic")

    await callback.answer()


@router.callback_query(F.data == "branch_create_redirect")
async def cb_branch_create_redirect(callback: CallbackQuery):
    """Handle redirect to /branch_create."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    _start_state.pop(chat_id, None)

    await callback.message.edit_text(
        "Use `/branch_create` or `/branch_create <name>` to create isolated worktree branch.",
        parse_mode="MarkdownV2"
    )
    await callback.answer()


@router.message(Command("branch_finish"))
async def cmd_branch_finish(message: Message):
    """Finish branch: merge and cleanup worktree."""
    if not is_admin(message.from_user.id):
        return

    if not await require_forum_group(message):
        return

    thread_id = message.message_thread_id
    project = project_manager.get_by_chat(message.chat.id)

    if not project:
        await message.answer("`[!]` Project not registered.", parse_mode="MarkdownV2")
        return

    thread = project.get_thread(thread_id)
    if not thread or not thread.worktree_path:
        await message.answer("`[!]` /branch_finish only works in worktree topics. Use /thread_close for this topic.", parse_mode="MarkdownV2")
        return

    # Check uncommitted changes
    from .git_utils import has_uncommitted_changes, branch_exists, get_default_branch
    worktree_path = Path(thread.worktree_path)

    if worktree_path.exists() and has_uncommitted_changes(worktree_path):
        await message.answer("`[!]` Uncommitted changes. Commit or stash first.", parse_mode="MarkdownV2")
        return

    # Build keyboard
    default_branch = get_default_branch(Path(project.cwd))
    buttons = [[InlineKeyboardButton(text=f"Merge -> {default_branch}", callback_data=f"bf_merge:{thread_id}:{default_branch}")]]

    # Add base_branch option if it exists and is different
    if thread.base_branch and thread.base_branch != default_branch:
        if branch_exists(Path(project.cwd), thread.base_branch):
            buttons.append([InlineKeyboardButton(text=f"Merge -> {thread.base_branch}", callback_data=f"bf_merge:{thread_id}:{thread.base_branch}")])

    buttons.append([InlineKeyboardButton(text="[!!] Delete without merge", callback_data=f"bf_delete:{thread_id}")])
    buttons.append([InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(f"Finish `{thread.name}` branch:", reply_markup=keyboard, parse_mode="MarkdownV2")


@router.callback_query(F.data.startswith("bf_merge:"))
async def cb_branch_finish_merge_confirm(callback: CallbackQuery):
    """Show merge confirmation."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    parts = callback.data.split(":")
    thread_id = int(parts[1])
    target_branch = parts[2]

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    # Check target has no uncommitted changes
    from .git_utils import has_uncommitted_changes
    if has_uncommitted_changes(Path(project.cwd)):
        await callback.message.edit_text("`[!]` Uncommitted changes in target directory. Commit or stash first.", parse_mode="MarkdownV2")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes, finish", callback_data=f"bf_do_merge:{thread_id}:{target_branch}")],
        [InlineKeyboardButton(text="[x] Cancel", callback_data="cancel")]
    ])

    await callback.message.edit_text(
        f"Merge `{thread.name}` -> `{target_branch}` will:\n"
        "- Merge branch and push\n"
        "- Close tmux session\n"
        f"- Delete {thread.worktree_path}\n"
        "- Archive topic\n\n"
        "Continue?",
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bf_do_merge:"))
async def cb_branch_finish_do_merge(callback: CallbackQuery):
    """Execute merge and cleanup."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    parts = callback.data.split(":")
    thread_id = int(parts[1])
    target_branch = parts[2]

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await callback.message.edit_text(f"`[~]` Merging {thread.name} -> {target_branch}...", parse_mode="MarkdownV2")
    await callback.answer()

    from .worktree import merge_branch, push_branch

    main_repo = Path(project.cwd)
    branch_name = thread.name

    # Merge
    result = merge_branch(main_repo, branch_name, target_branch)
    if not result.success:
        if "conflicts" in result.error.lower():
            await callback.message.edit_text("`[!]` Merge conflicts. Resolve and run /branch_finish again.", parse_mode="MarkdownV2")
        else:
            await callback.message.edit_text(f"`[x]` Merge failed: {result.error}", parse_mode="MarkdownV2")
        return

    # Push (optional, don't fail on error)
    push_result = push_branch(main_repo, target_branch)
    push_warning = "" if push_result.success else "\n`[!]` Push failed. Run `git push` manually."

    # Cleanup
    await _do_branch_cleanup(callback.message, project, thread, force=False)

    await callback.message.edit_text(f"`[v]` Branch {branch_name} merged and cleaned up{push_warning}", parse_mode="MarkdownV2")


@router.callback_query(F.data.startswith("bf_delete:"))
async def cb_branch_finish_delete_confirm(callback: CallbackQuery):
    """Show delete confirmation."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    parts = callback.data.split(":")
    thread_id = int(parts[1])

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes, delete", callback_data=f"bf_do_delete:{thread_id}")],
        [InlineKeyboardButton(text="[x] Cancel", callback_data="cancel")]
    ])

    await callback.message.edit_text(
        f"`[!]` Delete branch `{thread.name}` WITHOUT merging?\n\n"
        "This will:\n"
        "- Close tmux session\n"
        f"- Delete {thread.worktree_path}\n"
        f"- Delete branch `{thread.name}`\n"
        "- Archive topic\n\n"
        "All uncommitted work will be LOST.",
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bf_do_delete:"))
async def cb_branch_finish_do_delete(callback: CallbackQuery):
    """Execute delete without merge."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    parts = callback.data.split(":")
    thread_id = int(parts[1])

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await callback.message.edit_text(f"`[~]` Deleting {thread.name}...", parse_mode="MarkdownV2")
    await callback.answer()

    await _do_branch_cleanup(callback.message, project, thread, force=True)

    await callback.message.edit_text(f"`[v]` Branch {thread.name} deleted", parse_mode="MarkdownV2")


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
        await message.answer("`[x]` Branch creation failed. Check the new topic for details.", parse_mode="MarkdownV2")


@router.message(Command("my_chat_id"))
async def cmd_my_chat_id(message: Message):
    """Show user's chat ID - available to everyone."""
    thread_id = message.message_thread_id
    thread_info = f"\nThread ID: `{thread_id}`" if thread_id else "\nThread ID: None (General)"
    await message.answer(f"Your user ID: `{message.from_user.id}`\nThis chat ID: `{message.chat.id}`{thread_info}", parse_mode="MarkdownV2")

@router.message(Command("esc"))
async def cmd_esc(message: Message):
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        return

    # Get correct thread (topic or main)
    thread = project.threads.get(thread_id)
    if not thread:
        return

    if not project.cwd:
        logger.error(f"esc: project {project.project_name} has no cwd")
        return

    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_key("Escape")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Show available commands."""
    if not is_admin(message.from_user.id):
        return

    text = """**Commands**

`/start` — Start Claude / show status
`/new` — Start new Claude session
`/restart` — Kill and restart Claude tmux

**Threads**
`/thread_create [name]` — Create new Claude thread
`/thread_delete` — Delete thread (in topic)

**Git worktrees**
`/branch_create [name]` — Create worktree + thread
`/branch_finish` — Merge and cleanup

**Settings**
`/settings` — Show current settings
`/auto_accept` — Toggle auto-accept
`/auto_accept reset all` — Reset all to off

**Other**
`/esc` — Send Escape to Claude
`/my_chat_id` — Show your user ID"""

    await message.answer(text, parse_mode="MarkdownV2")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Show current settings."""
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("No project. Use /start first.")
        return

    thread = None
    if thread_id and project.threads:
        thread = project.threads.get(thread_id)

    if thread:
        auto_status = "⚡ ON" if thread.auto_accept else "OFF"
        text = (
            f"**Settings** (thread `{thread.name}`)\n\n"
            f"Auto-accept: {auto_status}"
        )
    else:
        auto_status = "⚡ ON" if project.auto_accept else "OFF"
        text = (
            f"**Settings** (`{project.project_name}`)\n\n"
            f"Auto-accept: {auto_status}"
        )

    await message.answer(text, parse_mode="MarkdownV2")


@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message):
    """Toggle auto-accept or reset all."""
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("No project. Use /start first.")
        return

    thread = None
    if thread_id and project.threads:
        thread = project.threads.get(thread_id)

    args = (message.text or "").split()[1:]

    # /auto_accept reset all - reset all to off
    if len(args) >= 2 and args[0].lower() == "reset" and args[1].lower() == "all":
        project.auto_accept = False
        if project.threads:
            for t in project.threads.values():
                t.auto_accept = False
        project_manager._save()
        await message.answer("Auto-accept reset to **OFF** for project and all threads.", parse_mode="MarkdownV2")
        return

    # /auto_accept - toggle current context
    if thread:
        thread.auto_accept = not thread.auto_accept
        status = "⚡ ON" if thread.auto_accept else "OFF"
        await message.answer(f"Auto-accept for `{thread.name}`: **{status}**", parse_mode="MarkdownV2")
    else:
        project.auto_accept = not project.auto_accept
        status = "⚡ ON" if project.auto_accept else "OFF"
        await message.answer(f"Auto-accept: **{status}**", parse_mode="MarkdownV2")
    project_manager._save()


@router.message(Command("resume"))
async def cmd_resume(message: Message):
    """Handle /resume command - not supported in multi-session mode."""
    thread_id = message.message_thread_id
    if thread_id is not None:
        # In a topic - resume not supported
        await message.answer(
            "`[!]` /resume not supported in multi-session mode.\n"
            "Use /thread_create for a new thread.",
            parse_mode="MarkdownV2"
        )
    else:
        # In private/general - just inform
        await message.answer(
            "`[!]` /resume not supported.\n"
            "Use /start to connect to existing session.",
            parse_mode="MarkdownV2"
        )


async def _send_session_command(message: Message, command: str, status_text: str) -> bool:
    """Common logic for /new and /clear commands.

    Returns True if command was sent successfully, False otherwise.
    """
    if not is_admin(message.from_user.id):
        return False

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("Project not registered. Use /start")
        return False

    thread_id = message.message_thread_id
    thread = project.threads.get(thread_id)
    if not thread:
        await message.answer("Thread not found. Use /start")
        return False

    tmux_name = thread.get_tmux_session(project.project_name)

    if not is_tmux_session_exists(tmux_name):
        await message.answer("tmux session not found. Start Claude in terminal.")
        return False

    # NOTE: Do NOT cancel watcher here - let it continue watching old session.
    # _bind_thread_to_session will cancel it when new session is found.
    # This prevents thread becoming "dead" if user cancels the command in Claude.

    # Mark thread as awaiting new session
    thread.awaiting_new_session = True
    thread.start_requested_at = time.time()
    thread.last_sent_message = None
    project_manager._save()

    # Send command to tmux
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_keys(command)

    await message.answer(status_text)
    return True


@router.message(Command("new"))
async def cmd_new(message: Message):
    """Start new Claude session in current thread."""
    await _send_session_command(message, "/new", "`[~]` Creating new session...")


@router.message(Command("clear"))
async def cmd_clear(message: Message):
    """Clear Claude session and start fresh."""
    await _send_session_command(message, "/clear", "`[~]` Clearing session...")


@router.message(Command("restart"))
async def cmd_restart(message: Message):
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("No active session to restart.")
        return

    # Determine tmux session name
    if thread_id is not None:
        thread = project.threads.get(thread_id)
        if thread:
            tmux_name = thread.get_tmux_session(project.project_name)
        else:
            await message.answer("No active session to restart.")
            return
    else:
        # Main thread or legacy
        thread = project.threads.get(None)
        if thread:
            tmux_name = thread.get_tmux_session(project.project_name)
        elif project.tmux_session:
            tmux_name = project.tmux_session
        else:
            await message.answer("No active session to restart.")
            return

    # Check if tmux exists
    if not is_tmux_session_exists(tmux_name):
        await message.answer("No active session to restart.")
        return

    # Store state for confirm callback
    _start_state[chat_id] = {
        "state": "restart_confirm",
        "tmux_name": tmux_name,
        "thread_id": thread_id,
    }

    await message.answer(
        f"Restart session `{tmux_name}`?",
        reply_markup=restart_confirm_keyboard(),
        parse_mode="MarkdownV2",
    )


@router.callback_query(F.data == "restart:confirm")
async def on_restart_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)

    if not state or state.get("state") != "restart_confirm":
        await callback.answer("Session expired")
        return

    tmux_name = state.get("tmux_name")
    thread_id = state.get("thread_id")
    _start_state.pop(chat_id, None)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Session not found")
        return

    # Get thread if in topic
    thread = None
    if thread_id is not None:
        thread = project.threads.get(thread_id)
    else:
        thread = project.threads.get(None)

    # Stop thread tasks
    if thread:
        if thread.poller_task and not thread.poller_task.done():
            thread.poller_task.cancel()
            try:
                await thread.poller_task
            except asyncio.CancelledError:
                pass
            thread.poller_task = None

        if thread.watcher_task and not thread.watcher_task.done():
            thread.watcher_task.cancel()
            try:
                await thread.watcher_task
            except asyncio.CancelledError:
                pass
            thread.watcher_task = None

        # Clear thread session data
        thread.session_id = None
        thread.jsonl_path = None
    else:
        # Legacy: stop project-level tasks
        if project.poller_task and not project.poller_task.done():
            project.poller_task.cancel()
            try:
                await project.poller_task
            except asyncio.CancelledError:
                pass
            project.poller_task = None

        if project.watcher_task and not project.watcher_task.done():
            project.watcher_task.cancel()
            try:
                await project.watcher_task
            except asyncio.CancelledError:
                pass
            project.watcher_task = None

        # Clear project session data
        project.session_id = None
        project.jsonl_path = None
        project.tmux_session = None

    # Kill tmux if exists
    if tmux_name and is_tmux_session_exists(tmux_name):
        import subprocess
        subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    project_manager._save()

    await callback.message.edit_text("Session stopped. Use /start to launch.")
    await callback.answer()


@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery):
    await callback.message.edit_text("Cancelled.")
    await callback.answer()


@router.callback_query(F.data.startswith("perm:"))
async def on_permission_callback(callback: CallbackQuery):
    """Handle permission button press."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    # Parse callback data: perm:{action}:{tmux_session}
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid callback format")
        return

    action = parts[1]
    tmux_session = parts[2]

    # Protection: project not found
    project = project_manager.get_by_tmux(tmux_session)
    if not project:
        await callback.answer("Session not found")
        return

    if not project.cwd:
        await callback.answer("Project has no cwd")
        return

    # Protection: tmux no longer exists
    tmux = TmuxSession(tmux_session, project.cwd)
    if not tmux.exists():
        await callback.answer("Tmux session closed")
        return

    chat_id = callback.message.chat.id
    kb_msg_id = callback.message.message_id

    # Delete content messages
    content_ids = permission_messages.pop(kb_msg_id, [])
    for msg_id in content_ids:
        try:
            await callback.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    # Delete keyboard message
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Send key to tmux
    if action == "esc":
        tmux.send_key("Escape")
    else:
        tmux.send_key(action)

    await callback.answer()


@router.callback_query(F.data.startswith("select_tmux:"))
async def on_tmux_selected(callback: CallbackQuery):
    """Handle tmux selection callback."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    # Parse callback data safely
    try:
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer("Invalid selection data")
            return
        _, project_name, tmux_session = parts
    except Exception:
        await callback.answer("Error processing selection")
        return

    project = project_manager.get_or_create(project_name)
    project.tmux_session = tmux_session

    await callback.message.edit_text(f"Connected to tmux: `{tmux_session}`", parse_mode="MarkdownV2")
    await callback.answer()

    # Refresh session and start tasks
    start_poller, start_watcher = _make_task_starters(callback.bot)
    project_manager.refresh_project_session(project)
    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()

    await send_with_retry(
        callback.message,
        f"Claude running in `{project.tmux_session}`\n\n"
        f"Attach: `tmux attach -t {project.tmux_session}`",
    )


@router.callback_query(F.data == "start:launch_claude")
async def on_start_launch_claude(callback: CallbackQuery):
    """Handle launch Claude button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Session expired, start again with /start")
        return

    project = project_manager.get_or_create(state["project"])
    project.chat_id = chat_id
    project.cwd = state["path"]

    # Get or create main thread
    thread = project.get_or_create_thread(None, "main")

    # Race protection: check if launch already in progress
    if thread.launch_task and not thread.launch_task.done():
        await callback.answer("Launch already in progress...")
        return

    await callback.answer()
    _start_state.pop(chat_id, None)

    from .launch_animation import launch_with_animation
    from .main import telegram_queue

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot,
            chat_id=chat_id,
            thread_id=None,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )

    project_manager._save()


@router.callback_query(F.data == "start:cancel")
async def on_start_cancel(callback: CallbackQuery):
    """Handle cancel button."""
    chat_id = callback.message.chat.id
    _start_state.pop(chat_id, None)
    await callback.message.edit_text("Cancelled.")
    await callback.answer()


@router.message()
async def on_message(message: Message):
    """Handle regular messages."""
    # Log incoming message
    text_preview = message.text[:100] if message.text else '<no text>'
    thread_id = message.message_thread_id
    logger.info(f"Incoming message from user={message.from_user.id} chat={message.chat.id} thread={thread_id}: {text_preview}")

    if not is_admin(message.from_user.id):
        logger.debug(f"Ignored: not admin (user={message.from_user.id})")
        return

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
                    parse_mode="MarkdownV2",
                )
                return
            if len(project_name) > 35:
                await message.answer(
                    "`[!]` Project name too long (max 35 chars). "
                    "Rename group or use /register_dir with shorter name.",
                    parse_mode="MarkdownV2",
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
                await message.answer(f"Directory `{path}` does not exist.", parse_mode="MarkdownV2")
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
