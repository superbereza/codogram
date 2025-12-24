# src/telegram_bridge/bot.py
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command

from .config import settings
from .tmux import TmuxSession

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
    await message.answer(
        f"Bridge ready.\n"
        f"Project: `{settings.project_dir}`\n"
        f"Attach: `{s.attach_command()}`",
        parse_mode="Markdown"
    )

@router.message(Command("attach"))
async def cmd_attach(message: Message):
    s = get_session()
    await message.answer(f"`{s.attach_command()}`", parse_mode="Markdown")

@router.message(Command("esc"))
async def cmd_esc(message: Message):
    """Send Escape key to tmux (not in menu)."""
    if message.chat.id != settings.chat_id:
        return
    s = get_session()
    s.send_key("Escape")

@router.message()
async def on_message(message: Message):
    if message.chat.id != settings.chat_id:
        return
    if not message.text:
        return

    s = get_session()
    s.send(message.text)
    # Don't send confirmation - watcher will show output
