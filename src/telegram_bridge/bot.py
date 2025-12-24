# src/telegram_bridge/bot.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from .config import settings
from .session_manager import manager
from .tmux import TmuxSession
from .state import permission_messages

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

    # Auto-register project by chat title
    if message.chat.title:
        existing = manager.get_chat_id(message.chat.title)
        if not existing:
            manager.register_project(message.chat.title, message.chat.id)

    session = manager.get_session_by_chat(message.chat.id)
    if session:
        tmux = TmuxSession(session.tmux_session, session.cwd)
        text = f"Bridge active.\nProject: `{session.project_name}`\nAttach: `{tmux.attach_command()}`"
    else:
        text = "Bridge ready. No active Claude session."

    try:
        await message.answer(text, parse_mode="Markdown")
    except Exception:
        await message.answer(text)

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
