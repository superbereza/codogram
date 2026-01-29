# src/codogram/handlers/settings/__init__.py
"""Settings handlers - display settings, toggles, verbose menu, reset."""
from aiogram import Router

from .main import router as main_router
from .verbose_menu import router as verbose_menu_router
from .reset import router as reset_router

router = Router(name="settings")
router.include_router(main_router)
router.include_router(verbose_menu_router)
router.include_router(reset_router)

__all__ = ["router"]
