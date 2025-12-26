# src/telegram_bridge/bot.py
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from .config import settings
from .session_manager import project_manager, ProjectState
from .tmux import TmuxSession
from .state import permission_messages
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

def get_session_for_chat(chat_id: int) -> TmuxSession | None:
    """Get TmuxSession for chat_id."""
    project = project_manager.get_by_chat(chat_id)
    if project and project.tmux_session:
        return TmuxSession(project.tmux_session, project.cwd or "/tmp")
    return None

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Start command - setup project and discover tmux + session."""
    import asyncio

    if not is_admin(message.from_user.id):
        return

    # Parse args
    args = message.text.split()[1:]  # Skip /start
    if len(args) < 2:
        await message.answer("Usage: /start <project_name> <cwd>")
        return

    project_name = args[0]
    cwd = args[1]

    # Save to config
    project = project_manager.get_or_create(project_name)
    project.chat_id = message.chat.id
    project.cwd = cwd

    # Phase 1: Discover tmux (for poller)
    from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention
    tmux_list = find_all_tmux_by_cwd(cwd)

    if len(tmux_list) == 0:
        # Fallback to convention
        tmux_by_convention = find_tmux_by_convention(project_name)
        if tmux_by_convention:
            project.tmux_session = tmux_by_convention
            await message.answer(f"Found tmux by convention: {tmux_by_convention}")
        else:
            await message.answer(f"⚠️ No tmux session found for {cwd}")
            # Still save and continue - user might start tmux later
    elif len(tmux_list) == 1:
        project.tmux_session = tmux_list[0]
        await message.answer(f"Connected to tmux: {tmux_list[0]}")
    else:
        # Multiple tmux - show selection keyboard
        keyboard = create_tmux_selection_keyboard(tmux_list, project_name)
        await message.answer(
            f"Multiple tmux sessions found for {cwd}:\n\n"
            "Select which one to connect:",
            reply_markup=keyboard
        )
        project_manager._save()
        return  # Wait for callback, don't start tasks yet

    # Phase 2: Discover session_id (for watcher)
    project_manager.refresh_project_session(project)
    if project.session_id:
        await message.answer(f"Found session: {project.session_id[:8]}...")
    else:
        await message.answer("No active Claude session found (will auto-discover)")

    # Start tasks
    # Define task starters (same pattern as existing code)
    bot = message.bot
    async def start_poller(p: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p)

    async def start_watcher(p: ProjectState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p)

    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()


async def launch_claude_new(message: Message, project: ProjectState, start_poller, start_watcher):
    """Launch Claude in tmux session using new ProjectState."""
    import asyncio
    import subprocess

    convention = f"claude-{project.project_name}"

    # Case 2: Our tmux exists - reuse
    if project.tmux_session == convention and is_tmux_session_exists(convention):
        subprocess.run(["tmux", "send-keys", "-t", convention, "claude", "Enter"], capture_output=True)
    # Case 3: Foreign tmux - create new alongside
    elif project.tmux_session and project.tmux_session != convention and is_tmux_session_exists(project.tmux_session):
        create_tmux_with_claude(convention, project.cwd)
        project.tmux_session = convention
    # Case 4: No tmux - create
    else:
        create_tmux_with_claude(convention, project.cwd)
        project.tmux_session = convention

    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()

    await message.answer(
        f"Claude запущен в `{project.tmux_session}`\n"
        f"Подключиться: `tmux attach -t {project.tmux_session}`\n\n"
        f"⏳ Ожидаю регистрацию...",
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
        f"Директория `{state['path']}` создана.\n\nНастроить гит?",
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

        # Define task starters
        bot = callback.bot
        async def start_poller(p: ProjectState):
            from .permission_poller import create_poller_task
            return await create_poller_task(bot, p)

        async def start_watcher(p: ProjectState):
            from .watcher import create_watcher_task
            return await create_watcher_task(bot, p)

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

        # Define task starters
        bot = callback.bot
        async def start_poller(p: ProjectState):
            from .permission_poller import create_poller_task
            return await create_poller_task(bot, p)

        async def start_watcher(p: ProjectState):
            from .watcher import create_watcher_task
            return await create_watcher_task(bot, p)

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

    # Define task starters
    bot = callback.bot
    async def start_poller(p: ProjectState):
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p)

    async def start_watcher(p: ProjectState):
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p)

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
    await project_manager._stop_tasks(project)

    # Kill tmux if exists
    if project.tmux_session and is_tmux_session_exists(project.tmux_session):
        import subprocess
        subprocess.run(["tmux", "kill-session", "-t", project.tmux_session], capture_output=True)

    # Clear session data
    project.claude_session_id = None
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
    action = callback.data.split(":")[1]
    tmux = get_session_for_chat(chat_id)

    if tmux:
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

    await callback.message.edit_text(f"✅ Connected to tmux: {tmux_session}")
    await callback.answer()

    # Define task starters
    bot = callback.bot
    async def start_poller(p: ProjectState):
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p)

    async def start_watcher(p: ProjectState):
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p)

    # Refresh session and start tasks
    project_manager.refresh_project_session(project)
    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()

    if project.session_id:
        await callback.message.answer(f"Found session: {project.session_id[:8]}...")
    else:
        await callback.message.answer("No active Claude session found (will auto-discover)")


@router.message()
async def on_message(message: Message):
    if not is_admin(message.from_user.id):
        return

    if not message.text:
        return

    chat_id = message.chat.id

    # Check if we're in conversation flow
    state = _start_state.get(chat_id)
    if state:
        if state["state"] == "awaiting_custom_path":
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

            # Define task starters
            bot = message.bot
            async def start_poller(p: ProjectState):
                from .permission_poller import create_poller_task
                return await create_poller_task(bot, p)

            async def start_watcher(p: ProjectState):
                from .watcher import create_watcher_task
                return await create_watcher_task(bot, p)

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

            # Define task starters
            bot = message.bot
            async def start_poller(p: ProjectState):
                from .permission_poller import create_poller_task
                return await create_poller_task(bot, p)

            async def start_watcher(p: ProjectState):
                from .watcher import create_watcher_task
                return await create_watcher_task(bot, p)

            _start_state.pop(chat_id, None)
            await launch_claude_new(message, project, start_poller, start_watcher)
            return

    # Normal message - send to tmux
    tmux = get_session_for_chat(chat_id)
    if tmux:
        tmux.send(message.text)
    else:
        # No active session - only respond in group chats
        if message.chat.id < 0:  # Negative IDs are groups/channels
            await message.answer("Нет активной сессии Claude. Используй /start для запуска.")
