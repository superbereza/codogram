"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions, start, new_chat, threads, branches, sessions, settings, shift_tab, finish_chat, common, messages, migration, audio, dm, members, ask_user
from .setup import setup_router


def register_handlers(dp: Dispatcher):
    """Register all handler routers.

    Note: AdminMiddleware is registered on dp level in main.py,
    protecting ALL routers. No need to add it here.

    Order matters:
    - Specific command handlers first
    - common.router has cb_cancel (generic cancel)
    - messages.router is catch-all (must be last)
    """
    dp.include_router(migration.router)      # Migration events (must be early)
    dp.include_router(setup_router)          # Setup flow (my_chat_member, onboarding)
    dp.include_router(permissions.router)   # Permission callbacks
    dp.include_router(ask_user.router)      # AskUserQuestion callbacks
    dp.include_router(dm.router)            # DM onboarding (BEFORE start!)
    dp.include_router(start.router)         # /start, /reset_chat + FSM
    dp.include_router(new_chat.router)      # /new_chat (unified)
    dp.include_router(threads.router)       # /thread aliases
    dp.include_router(branches.router)      # /branch aliases
    dp.include_router(sessions.router)      # /clear_context, /esc
    dp.include_router(settings.router)      # /settings, /auto_accept, /help
    dp.include_router(shift_tab.router)     # /shift_tab
    dp.include_router(finish_chat.router)   # /finish_chat
    dp.include_router(members.router)       # Member join/leave for emoji pack
    dp.include_router(common.router)        # cb_cancel
    dp.include_router(audio.router)         # Voice/audio transcription via Whisper
    dp.include_router(messages.router)      # Catch-all for tmux routing (LAST!)
