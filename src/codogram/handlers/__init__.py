"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions, start, threads, branches, sessions, settings, shift_tab, finish, create_flow, common, messages, migration


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
    dp.include_router(permissions.router)   # Permission callbacks
    dp.include_router(start.router)         # /start, /restart + FSM
    dp.include_router(threads.router)       # /thread_create, /thread_delete
    dp.include_router(branches.router)      # /branch_create, /branch_finish
    dp.include_router(sessions.router)      # /new, /clear, /esc, /resume
    dp.include_router(settings.router)      # /settings, /auto_accept, /help
    dp.include_router(shift_tab.router)     # /shift_tab
    dp.include_router(finish.router)        # /finish
    dp.include_router(create_flow.router)   # Create flow name selection
    dp.include_router(common.router)        # cb_cancel
    dp.include_router(messages.router)      # Catch-all for tmux routing (LAST!)
