# src/telegram_bridge/bot.py
from pathlib import Path
import asyncio
import re

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from .config import settings
from .session_manager import project_manager, ProjectState
from .tmux import TmuxSession
from .state import permission_messages
from .logging_config import logger
from .project_launcher import (
    resolve_project_path,
    is_tmux_session_exists,
    create_tmux_with_claude,
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

def get_session_for_chat(chat_id: int) -> TmuxSession | None:
    """Get TmuxSession for chat_id."""
    project = project_manager.get_by_chat(chat_id)
    if project and project.tmux_session:
        return TmuxSession(project.tmux_session, project.cwd or "/tmp")
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
        f"**Claude активен**",
        f"",
        f"Проект: `{project.project_name}`",
        f"Путь: `{project.cwd}`",
        f"Tmux: `{project.tmux_session}`",
    ]

    if project.session_id:
        status_lines.append(f"Session: `{project.session_id[:8]}...`")

    status_lines.extend([
        "",
        f"Подключиться: `tmux attach -t {project.tmux_session}`",
    ])

    await message.answer("\n".join(status_lines), parse_mode="Markdown")

def _make_task_starters(bot):
    """Create task starter functions for poller and watcher.

    Returns:
        (start_poller, start_watcher) - async functions to start tasks
    """
    async def start_poller(p: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p)

    async def start_watcher(p: ProjectState, send_missed: bool = False) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p, send_missed)

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
            f"Директория `{path}` не найдена.\n\nЧто делать?",
            reply_markup=dir_not_found_keyboard(),
            parse_mode="Markdown",
        )

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
                f"Claude не запущен в `{cwd}`.\n\nЗапустить?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Да, запустить", callback_data="start:launch_claude"),
                        InlineKeyboardButton(text="Нет", callback_data="start:cancel"),
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

    await message.answer(
        f"Claude запущен в `{project.tmux_session}`\n"
        f"Подключиться: `tmux attach -t {project.tmux_session}`",
        parse_mode="Markdown",
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
    args = message.text.split()[1:]  # Skip /start

    # Case 1: Project name provided
    if args:
        project_name = args[0]
        if not is_valid_project_name(project_name):
            await message.answer(
                "Имя проекта может содержать только буквы, цифры, `-` и `_`.",
                parse_mode="Markdown",
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
        await _start_project_flow(message, project)
        return

    # Case 3: New chat - use chat title as project name
    chat_title = message.chat.title
    if chat_title:
        # Sanitize title to valid project name (replace spaces with -, remove invalid chars)
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', chat_title)
        sanitized = re.sub(r'-+', '-', sanitized).strip('-')  # Collapse multiple dashes
        if sanitized and is_valid_project_name(sanitized):
            project = project_manager.get_or_create(sanitized)
            project.chat_id = chat_id
            await _start_project_flow(message, project)
            return

    # Fallback: ask for project name (private chat or invalid title)
    _start_state[chat_id] = {"state": "awaiting_project_name"}
    await message.answer(
        "Отправь имя проекта (например: `my-project`):",
        parse_mode="Markdown",
    )


async def launch_claude_new(message: Message, project: ProjectState, start_poller, start_watcher):
    """Launch Claude in tmux session using new ProjectState."""
    import subprocess

    convention = f"claude-{project.project_name}"

    # Block HistoryWatcher from grabbing old session during startup
    project.awaiting_new_session = True

    # Wait before showing anything
    await asyncio.sleep(3.0)

    # Case 1: Our tmux exists - reuse
    if project.tmux_session == convention and is_tmux_session_exists(convention):
        subprocess.run(["tmux", "send-keys", "-t", convention, "claude", "Enter"], capture_output=True)
    # Case 2: Foreign tmux - create new alongside
    elif project.tmux_session and project.tmux_session != convention and is_tmux_session_exists(project.tmux_session):
        result = create_tmux_with_claude(convention, project.cwd)
        if not result.success:
            await message.answer(f"Ошибка запуска: {result.error}")
            return
        project.tmux_session = convention
    # Case 3: No tmux - create
    else:
        result = create_tmux_with_claude(convention, project.cwd)
        if not result.success:
            await message.answer(f"Ошибка запуска: {result.error}")
            return
        project.tmux_session = convention

    # Start animation
    tmux = TmuxSession(project.tmux_session, project.cwd)
    status_msg = await message.answer("`[._.]`", parse_mode="Markdown")

    # Doom-guy frustration animation
    faces = [
        # Sleeping / waking up
        "[._.]",
        "[._.]",
        "[-_-]",
        "[-_-]",
        "[.o.]",
        "[o_o]",
        # Alert, waiting
        "[o_o]",
        "[◉_◉]",
        "[◉_◉]",
        "[◉_◉]",
        # Getting tense
        "[◉︿◉]",
        "[◉~◉]",
        "[°_°]",
        "[°_°]",
        # Confusion
        "[°□°]",
        "[°□°]",
        # Frustration builds
        "[ಠ_ಠ]",
        "[ಠ_ಠ]",
        "[ಠ︿ಠ]",
        "[ಠ益ಠ]",
        # Panic
        "[>_<]",
        "[>︿<]",
        "[>△<]",
        # Overload
        "[×_×]",
        "[×_×]",
        "[✖_✖]",
        "[✖益✖]",
        # Death
        "[☠_☠]",
        "[☠_☠]",
        # Restart
        "[._.]",
    ]

    frame = 0
    for _ in range(60):  # max 60 seconds
        if tmux.is_claude_ready():
            break
        face = faces[frame % len(faces)]
        try:
            await status_msg.edit_text(f"`{face}`", parse_mode="Markdown")
        except Exception:
            pass  # Ignore flood control
        await asyncio.sleep(1.5)  # 1.5s between frames - safe for Telegram
        frame += 1

    # Extra delay to ensure Claude's input is truly ready
    await asyncio.sleep(1.0)

    # Happy face when ready
    try:
        await status_msg.edit_text("`[≖‿≖] Ready!`", parse_mode="Markdown")
        await asyncio.sleep(1.0)
    except Exception:
        pass

    # Delete status message
    try:
        await status_msg.delete()
    except Exception:
        pass

    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()

    await message.answer(
        f"Claude запущен в `{project.tmux_session}`\n"
        f"Подключиться: `tmux attach -t {project.tmux_session}`",
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "start:create_dir")
async def on_start_create_dir(callback: CallbackQuery):
    """Handle create directory button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Сессия истекла, начни заново с /start")
        return

    # Create directory
    result = create_project_directory(state["path"])
    if not result.success:
        await callback.message.edit_text(f"Ошибка создания директории: {result.error}")
        await callback.answer()
        return

    # Ask about git
    state["state"] = "awaiting_git_choice"
    await callback.message.edit_text(
        f"Директория `{state['path']}` создана.\n\n"
        f"**Настроить гит?**\n\n"
        f"• `git init` — локальный репозиторий\n"
        f"• `git init + gh repo create` — создать и на GitHub\n"
        f"• `git clone` — клонировать существующий\n"
        f"• Без гита — пустая папка",
        reply_markup=git_setup_keyboard(),
        parse_mode="Markdown",
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
        await callback.answer("Сессия истекла")
        return

    state["state"] = "awaiting_custom_path"
    await callback.message.edit_text("Отправь путь к директории проекта:")
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
        await callback.answer("Сессия истекла")
        return

    result = git_init(state["path"])
    if not result.success:
        await callback.message.edit_text(f"Ошибка git init: {result.error}")
    else:
        await callback.message.edit_text("Git инициализирован. Запускаю Claude...")

        # Get or create project
        project = project_manager.get_or_create(state["project"])
        project.cwd = state["path"]

        start_poller, start_watcher = _make_task_starters(callback.bot)
        await launch_claude_new(callback.message, project, start_poller, start_watcher)

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
        await callback.answer("Сессия истекла")
        return

    state["state"] = "awaiting_gh_visibility"
    await callback.message.edit_text(
        "Видимость репозитория?",
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
        await callback.answer("Сессия истекла")
        return

    private = callback.data == "start:gh_private"
    await callback.message.edit_text("Создаю репозиторий на GitHub...")

    result = git_init_with_github(state["path"], private=private)
    if not result.success:
        await callback.message.edit_text(f"Ошибка: {result.error}")
    else:
        await callback.message.edit_text("Репозиторий создан. Запускаю Claude...")

        # Get or create project
        project = project_manager.get_or_create(state["project"])
        project.cwd = state["path"]

        start_poller, start_watcher = _make_task_starters(callback.bot)
        await launch_claude_new(callback.message, project, start_poller, start_watcher)

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
        await callback.answer("Сессия истекла")
        return

    state["state"] = "awaiting_clone_url"
    await callback.message.edit_text(
        "Отправь ссылку на репозиторий:\n"
        "• SSH: `git@github.com:user/repo.git`\n"
        "• HTTPS: `https://github.com/user/repo.git`",
        parse_mode="Markdown",
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
        await callback.answer("Сессия истекла")
        return

    await callback.message.edit_text("Запускаю Claude...")

    # Get or create project
    project = project_manager.get_or_create(state["project"])
    project.cwd = state["path"]

    start_poller, start_watcher = _make_task_starters(callback.bot)
    await launch_claude_new(callback.message, project, start_poller, start_watcher)

    _start_state.pop(chat_id, None)
    await callback.answer()


@router.message(Command("my_chat_id"))
async def cmd_my_chat_id(message: Message):
    """Show user's chat ID - available to everyone."""
    await message.answer(f"Your user ID: `{message.from_user.id}`\nThis chat ID: `{message.chat.id}`", parse_mode="Markdown")

@router.message(Command("esc"))
async def cmd_esc(message: Message):
    if not is_admin(message.from_user.id):
        return

    tmux = get_session_for_chat(message.chat.id)
    if tmux:
        tmux.send_key("Escape")

@router.message(Command("restart_session"))
async def cmd_restart_session(message: Message):
    if not is_admin(message.from_user.id):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project or not project.tmux_session:
        await message.answer("Нет активной сессии для перезапуска.")
        return

    await message.answer(
        f"Перезапустить сессию `{project.tmux_session}`?",
        reply_markup=restart_confirm_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "restart:confirm")
async def on_restart_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Сессия не найдена")
        return

    # Stop tasks
    # Stop poller task
    if project.poller_task and not project.poller_task.done():
        project.poller_task.cancel()
        try:
            await project.poller_task
        except asyncio.CancelledError:
            pass
        project.poller_task = None

    # Stop watcher task
    if project.watcher_task and not project.watcher_task.done():
        project.watcher_task.cancel()
        try:
            await project.watcher_task
        except asyncio.CancelledError:
            pass
        project.watcher_task = None

    # Kill tmux if exists
    if project.tmux_session and is_tmux_session_exists(project.tmux_session):
        import subprocess
        subprocess.run(["tmux", "kill-session", "-t", project.tmux_session], capture_output=True)

    # Clear session data
    project.session_id = None
    project.jsonl_path = None
    project.tmux_session = None
    project_manager._save()

    await callback.message.edit_text("Сессия остановлена. Используй /start для запуска.")
    await callback.answer()


@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery):
    await callback.message.edit_text("Отменено.")
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

    # Protection: tmux no longer exists
    tmux = TmuxSession(tmux_session, project.cwd or "/tmp")
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

    await callback.message.edit_text(f"Подключено к tmux: `{tmux_session}`", parse_mode="Markdown")
    await callback.answer()

    # Refresh session and start tasks
    start_poller, start_watcher = _make_task_starters(callback.bot)
    project_manager.refresh_project_session(project)
    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()

    await callback.message.answer(
        f"Claude запущен в `{project.tmux_session}`\n"
        f"Подключиться: `tmux attach -t {project.tmux_session}`",
        parse_mode="Markdown",
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
        await callback.answer("Сессия истекла, начни заново с /start")
        return

    await callback.answer()  # Answer immediately to avoid timeout
    await callback.message.edit_text("Запускаю Claude...")

    project = project_manager.get_or_create(state["project"])
    project.chat_id = chat_id
    project.cwd = state["path"]

    start_poller, start_watcher = _make_task_starters(callback.bot)
    await launch_claude_new(callback.message, project, start_poller, start_watcher)

    _start_state.pop(chat_id, None)


@router.callback_query(F.data == "start:cancel")
async def on_start_cancel(callback: CallbackQuery):
    """Handle cancel button."""
    chat_id = callback.message.chat.id
    _start_state.pop(chat_id, None)
    await callback.message.edit_text("Отменено.")
    await callback.answer()


@router.message()
async def on_message(message: Message):
    # Log incoming message
    text_preview = message.text[:100] if message.text else '<no text>'
    logger.info(f"Incoming message from user={message.from_user.id} chat={message.chat.id}: {text_preview}")

    if not is_admin(message.from_user.id):
        logger.debug(f"Ignored: not admin (user={message.from_user.id})")
        return

    if not message.text:
        return

    chat_id = message.chat.id

    # Check if we're in conversation flow
    state = _start_state.get(chat_id)
    if state:
        if state["state"] == "awaiting_project_name":
            # User sent project name
            project_name = message.text.strip()
            if not project_name or not is_valid_project_name(project_name):
                await message.answer(
                    "Имя проекта может содержать только буквы, цифры, `-` и `_`.",
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
                await message.answer(f"Директория `{path}` не существует.", parse_mode="Markdown")
                return

            # Get or create project and save path
            project = project_manager.get_or_create(state["project"])
            project.chat_id = chat_id
            project.cwd = str(Path(path).expanduser())
            project_manager._save()

            start_poller, start_watcher = _make_task_starters(message.bot)
            _start_state.pop(chat_id, None)
            await launch_claude_new(message, project, start_poller, start_watcher)
            return

        elif state["state"] == "awaiting_clone_url":
            # User sent clone URL
            url = message.text.strip()
            await message.answer("Клонирую репозиторий...")

            result = git_clone(state["path"], url)
            if not result.success:
                await message.answer(f"Ошибка клонирования: {result.error}")
                return

            # Get or create project
            project = project_manager.get_or_create(state["project"])
            project.cwd = state["path"]

            start_poller, start_watcher = _make_task_starters(message.bot)
            _start_state.pop(chat_id, None)
            await launch_claude_new(message, project, start_poller, start_watcher)
            return

    # Normal message - check session and send to tmux
    project = project_manager.get_by_chat(chat_id)
    if project:
        start_poller, start_watcher = _make_task_starters(message.bot)

        if project.session_id is None:
            # No session bound - use session binding (match by user message)
            # This avoids grabbing an old session after /restart_session + /start
            from .history_watcher import poll_for_session

            project.last_sent_message = message.text

            # Start binding task if not already running
            if not project.binding_task or project.binding_task.done():
                project.binding_task = asyncio.create_task(
                    poll_for_session(project, message.bot, start_poller, start_watcher)
                )
        else:
            # Session already bound - check if it changed (user might have done /new in tmux)
            from .history_watcher import check_session_for_project
            await check_session_for_project(project, message.bot, start_poller, start_watcher)

    tmux = get_session_for_chat(chat_id)
    if tmux:
        tmux.send(message.text)
    else:
        # No active session - only respond in group chats
        if message.chat.id < 0:  # Negative IDs are groups/channels
            await message.answer("Нет активной сессии Claude. Используй /start для запуска.")
