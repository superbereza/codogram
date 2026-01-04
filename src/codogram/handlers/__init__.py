"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions, start, threads, branches


def register_handlers(dp: Dispatcher):
    """Register all handler routers.

    Note: All routers are protected by AdminMiddleware on dp level.
    No need to add middleware to individual routers.
    """
    dp.include_router(permissions.router)
    dp.include_router(start.router)
    dp.include_router(threads.router)
    dp.include_router(branches.router)
