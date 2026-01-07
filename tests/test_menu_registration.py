# tests/test_menu_registration.py
import os

# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_register_chat_menu_helper_exists():
    """_register_chat_menu helper should exist."""
    from codogram.handlers.start import _register_chat_menu
    import asyncio
    assert asyncio.iscoroutinefunction(_register_chat_menu)


@pytest.mark.asyncio
async def test_register_chat_menu_calls_service():
    """_register_chat_menu should delegate to register_menu_for_chat."""
    from codogram.handlers.start import _register_chat_menu

    bot = AsyncMock()
    chat = MagicMock()
    chat.id = 123
    chat.is_forum = True

    with patch("codogram.handlers.start.register_menu_for_chat") as reg_menu:
        await _register_chat_menu(bot, chat)
        reg_menu.assert_called_once_with(bot, 123, is_forum=True)


@pytest.mark.asyncio
async def test_register_chat_menu_handles_none_is_forum():
    """_register_chat_menu should handle is_forum=None as False."""
    from codogram.handlers.start import _register_chat_menu

    bot = AsyncMock()
    chat = MagicMock()
    chat.id = 456
    chat.is_forum = None

    with patch("codogram.handlers.start.register_menu_for_chat") as reg_menu:
        await _register_chat_menu(bot, chat)
        reg_menu.assert_called_once_with(bot, 456, is_forum=False)
