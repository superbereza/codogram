# src/codogram/handlers/setup/__init__.py
"""Setup flow handlers.

This module provides the new onboarding flow (v2) that triggers when:
1. Bot is added to a chat
2. /start in a chat without project
3. Any message in a chat without project

See docs/designs/2026-01-18-start-flow-v2.md for flow diagrams.
"""
from aiogram import Router

setup_router = Router(name="setup")

# Import routers after setup_router is defined to avoid circular imports
from . import triggers  # noqa: E402, F401
from . import admin_check  # noqa: E402, F401
from . import setup_type  # noqa: E402, F401
from . import clone_flow  # noqa: E402, F401
from . import connect_flow  # noqa: E402, F401
from . import new_project_flow  # noqa: E402, F401
from . import rename  # noqa: E402, F401

# Include sub-routers
setup_router.include_router(triggers.router)
setup_router.include_router(admin_check.router)
setup_router.include_router(setup_type.router)
setup_router.include_router(clone_flow.router)
setup_router.include_router(connect_flow.router)
setup_router.include_router(new_project_flow.router)
setup_router.include_router(rename.router)
