# src/codogram/handlers/start/__init__.py
"""Start flow handlers."""
from aiogram import Router

from .commands import router as commands_router
from .fsm import router as fsm_router
from .callbacks import router as callbacks_router

router = Router(name="start")
router.include_router(commands_router)
router.include_router(fsm_router)
router.include_router(callbacks_router)

__all__ = ["router"]
