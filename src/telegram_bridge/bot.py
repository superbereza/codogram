# src/telegram_bridge/bot.py
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from .config import settings
from .tmux import TmuxSession
from .state import permission_messages

router = Router()
session: TmuxSession | None = None

def get_session() -> TmuxSession:
    global session
    if session is None:
        session = TmuxSession(settings.tmux_session, settings.project_dir)
        session.create()
    return session

@router.message(Command("start"))
async def cmd_start(message: Message):
    s = get_session()
    text = f"Bridge ready.\nProject: `{settings.project_dir}`\nAttach: `{s.attach_command()}`"
    try:
        await message.answer(text, parse_mode="Markdown")
    except Exception:
        await message.answer(text)

@router.message(Command("attach"))
async def cmd_attach(message: Message):
    s = get_session()
    text = f"`{s.attach_command()}`"
    try:
        await message.answer(text, parse_mode="Markdown")
    except Exception:
        await message.answer(s.attach_command())

@router.message(Command("esc"))
async def cmd_esc(message: Message):
    """Send Escape key to tmux (not in menu)."""
    if message.chat.id != settings.chat_id:
        return
    s = get_session()
    s.send_key("Escape")

@router.callback_query(F.data.startswith("perm:"))
async def on_permission_callback(callback: CallbackQuery):
    """Handle permission button press."""
    if callback.message.chat.id != settings.chat_id:
        return

    kb_msg_id = callback.message.message_id

    # Delete content messages
    content_ids = permission_messages.pop(kb_msg_id, [])
    for msg_id in content_ids:
        try:
            await callback.bot.delete_message(settings.chat_id, msg_id)
        except Exception:
            pass

    # Delete keyboard message
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Send key to tmux
    action = callback.data.split(":")[1]
    s = get_session()

    if action == "esc":
        s.send_key("Escape")
    else:
        s.send_key(action)

    await callback.answer()

@router.message()
async def on_message(message: Message):
    if message.chat.id != settings.chat_id:
        return
    if not message.text:
        return

    s = get_session()
    s.send(message.text)
    # Don't send confirmation - watcher will show output
