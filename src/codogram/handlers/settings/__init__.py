# src/codogram/handlers/settings/__init__.py
"""Settings handlers - display settings, toggles, verbose menu."""
from aiogram import Router

from .main import router as main_router
from .verbose_menu import router as verbose_menu_router

router = Router(name="settings")
router.include_router(main_router)
router.include_router(verbose_menu_router)

__all__ = ["router"]
