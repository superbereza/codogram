# src/telegram_bridge/bot.py
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
    session_name = f"claude-{project_name}"

    # Check if session already exists
    if is_tmux_session_exists(session_name):
        # Kill old session
        import subprocess
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)

    result = create_tmux_with_claude(session_name, path)

    if result.success:
        await message.answer(
            f"Claude запущен в `{session_name}`\n"
            f"Подключиться: `tmux attach -t {session_name}`",
            parse_mode="Markdown",
        )
    else:
        await message.answer(f"Ошибка запуска: {result.error}")

@router.message(Command("register_dir"))
async def cmd_register_dir(message: Message):
    if not is_admin(message.from_user.id):
        return

    if not message.text:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /register_dir <path>\nExample: /register_dir personal-agent")
        return

    path = parts[1].strip()
    # path is relative to base_dir
    project_name = path.split("/")[-1]

    manager.register_project(project_name, message.chat.id)
    await message.answer(f"Registered `{project_name}` for this chat.", parse_mode="Markdown")

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

    tmux = get_session_for_chat(message.chat.id)
    if tmux:
        tmux.send(message.text)
    else:
        # No active session - only respond in group chats
        if message.chat.id < 0:  # Negative IDs are groups/channels
            await message.answer("No active Claude session. Start Claude in this project first.")
