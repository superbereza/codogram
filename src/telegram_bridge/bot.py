# src/telegram_bridge/bot.py
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from .config import settings
from .session_manager import manager
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
)

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
    session = manager.get_session_by_chat(chat_id)
    if session:
        return TmuxSession(session.tmux_session, session.cwd)
    return None

@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id

    # Auto-register project by chat title
    project_name = message.chat.title
    if not project_name:
        await message.answer("Эта команда работает только в групповых чатах с названием проекта.")
        return

    # Register project if not exists
    existing_chat = manager.get_chat_id(project_name)
    if not existing_chat:
        manager.register_project(project_name, chat_id)

    # Check if Claude already running
    session = manager.get_session_by_chat(chat_id)
    if session and session.poller_task and not session.poller_task.done():
        tmux = TmuxSession(session.tmux_session, session.cwd)
        if is_tmux_session_exists(session.tmux_session):
            text = f"Claude активен.\nПроект: `{session.project_name}`\nПодключиться: `{tmux.attach_command()}`"
            try:
                await message.answer(text, parse_mode="Markdown")
            except Exception:
                await message.answer(text)
            return

    # Resolve project path
    custom_path = manager.get_project_path(project_name)
    path_result = resolve_project_path(project_name, custom_path)

    if not path_result.exists:
        # Directory doesn't exist - ask what to do
        _start_state[chat_id] = {
            "state": "awaiting_dir_choice",
            "project": project_name,
            "path": path_result.path,
        }
        await message.answer(
            f"Директория `{path_result.path}` не найдена.",
            reply_markup=dir_not_found_keyboard(),
            parse_mode="Markdown",
        )
        return

    # Directory exists - launch Claude
    await launch_claude(message, project_name, path_result.path)


async def launch_claude(message: Message, project_name: str, path: str):
    """Launch Claude in tmux session."""
    import asyncio
    import subprocess

    session_name = f"claude-{project_name}"
    chat_id = message.chat.id

    # Check if session already exists
    if is_tmux_session_exists(session_name):
        # Kill old session
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)

    result = create_tmux_with_claude(session_name, path)

    if not result.success:
        await message.answer(f"Ошибка запуска: {result.error}")
        return

    await message.answer(
        f"Claude запущен в `{session_name}`\n"
        f"Подключиться: `tmux attach -t {session_name}`\n\n"
        f"⏳ Ожидаю регистрацию сессии...",
        parse_mode="Markdown",
    )

    # Wait for session to register (Claude's hook will call our HTTP endpoint)
    for _ in range(30):  # 30 seconds timeout
        await asyncio.sleep(1)
        session = manager.get_session_by_chat(chat_id)
        if session and session.poller_task and not session.poller_task.done():
            await message.answer("✅ Сессия готова! Можешь писать.")
            return

    await message.answer("⚠️ Сессия не зарегистрировалась за 30 сек. Проверь tmux.")


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
        await launch_claude(callback.message, state["project"], state["path"])

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
        await launch_claude(callback.message, state["project"], state["path"])

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
    await launch_claude(callback.message, state["project"], state["path"])

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

            # Save path and launch
            manager.register_project(state["project"], chat_id, path=path)
            _start_state.pop(chat_id, None)
            await launch_claude(message, state["project"], str(Path(path).expanduser()))
            return

        elif state["state"] == "awaiting_clone_url":
            # User sent clone URL
            url = message.text.strip()
            await message.answer("Клонирую репозиторий...")

            result = git_clone(state["path"], url)
            if not result.success:
                await message.answer(f"Ошибка клонирования: {result.error}")
                return

            _start_state.pop(chat_id, None)
            await launch_claude(message, state["project"], state["path"])
            return

    # Normal message - send to tmux
    tmux = get_session_for_chat(chat_id)
    if tmux:
        tmux.send(message.text)
    else:
        # No active session - only respond in group chats
        if message.chat.id < 0:  # Negative IDs are groups/channels
            await message.answer("Нет активной сессии Claude. Используй /start для запуска.")
