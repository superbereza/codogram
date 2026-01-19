# src/codogram/handlers/setup/__init__.py
"""Setup flow handlers.

This module provides the new onboarding flow (v2) that triggers when:
1. Bot is added to a chat
2. /start in a chat without project
3. Any message in a chat without project

See docs/designs/2026-01-18-start-flow-v2.md for flow diagrams.
"""
import re

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ... import strings

setup_router = Router(name="setup")

# Callback prefixes used in setup flow
SETUP_CALLBACK_PATTERN = re.compile(
    r"^(setup|folder|git|clone|rename|admin|error|name|exists):"
)


# --- Common handlers ---

@setup_router.callback_query(F.data == "noop")
async def on_noop(callback: CallbackQuery):
    """Acknowledge non-interactive button tap (e.g., pagination indicator)."""
    await callback.answer()

# Import routers after setup_router is defined to avoid circular imports
from . import triggers  # noqa: E402, F401
from . import admin_check  # noqa: E402, F401
from . import setup_type  # noqa: E402, F401
from . import clone_flow  # noqa: E402, F401
from . import connect_flow  # noqa: E402, F401
from . import new_project_flow  # noqa: E402, F401
from . import launch  # noqa: E402, F401

# Include sub-routers
# Order matters: specific state handlers first, triggers (catch-all) last
setup_router.include_router(admin_check.router)
setup_router.include_router(setup_type.router)
setup_router.include_router(clone_flow.router)
setup_router.include_router(connect_flow.router)
setup_router.include_router(new_project_flow.router)
setup_router.include_router(launch.router)
# triggers.router has on_any_message catch-all, must be LAST
setup_router.include_router(triggers.router)


# --- Fallback for stale callbacks (bot restarted, FSM state lost) ---

from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext

from ...logging_config import logger


class NoSetupFlowState(BaseFilter):
    """Filter that passes only if NOT in any SetupFlow state."""

    async def __call__(self, callback: CallbackQuery, state: FSMContext) -> bool:
        current_state = await state.get_state()
        # Pass only if no state or state is not SetupFlow
        return not (current_state and current_state.startswith("SetupFlow:"))


@setup_router.callback_query(F.data.regexp(SETUP_CALLBACK_PATTERN), NoSetupFlowState())
async def on_stale_setup_callback(callback: CallbackQuery):
    """Handle setup callbacks when FSM state is lost (e.g., after bot restart).

    Only triggers when there's no active SetupFlow state.
    """
    logger.info(f"Stale setup callback: {callback.data}")

    # Delete stale message with buttons
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete stale message: {e}")

    # Send restart notice
    await callback.message.answer(
        strings.SETUP_BOT_RESTARTED,
        parse_mode="MarkdownV2",
    )
    await callback.answer()
