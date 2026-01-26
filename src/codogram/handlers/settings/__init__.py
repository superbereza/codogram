# src/codogram/handlers/settings/__init__.py
"""Settings handlers - display settings, toggles, verbose menu."""
from aiogram import Router

from .main import router as main_router

router = Router(name="settings")
router.include_router(main_router)

__all__ = ["router"]
