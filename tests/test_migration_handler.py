# tests/test_migration_handler.py
import os

# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from codogram.handlers.migration import router, on_chat_migration
from codogram.strings import MIGRATION_SUCCESS


def test_router_exists():
    """Migration router should exist."""
    assert router is not None
    assert router.name == "migration"


def test_migration_message_format():
    """Migration message follows tone-of-voice."""
    assert "`[v]` Topics enabled" in MIGRATION_SUCCESS
    assert "/thread" in MIGRATION_SUCCESS
    assert "/branch" in MIGRATION_SUCCESS
    assert "/finish" in MIGRATION_SUCCESS


@pytest.mark.asyncio
async def test_migration_ignores_unknown_chat():
    """Migration handler ignores chats without registered project."""
    from codogram.core.session_manager import project_manager

    message = MagicMock()
    message.chat.id = 999999
    message.migrate_to_chat_id = 888888

    telegram_queue = AsyncMock()

    with patch.object(project_manager, 'get_by_chat', return_value=None):
        await on_chat_migration(message, telegram_queue)

    # Should not send any message
    telegram_queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_migration_updates_project():
    """Migration handler updates chat_id and sends notification."""
    from codogram.handlers.migration import on_chat_migration

    message = MagicMock()
    message.chat.id = 111111
    message.migrate_to_chat_id = 222222
    message.bot = MagicMock()

    mock_project = MagicMock()
    mock_project.chat_id = 111111
    mock_project.project_name = "test-project"

    telegram_queue = AsyncMock()

    with patch("codogram.handlers.migration.project_manager") as mock_pm, \
         patch("codogram.handlers.migration.register_menu_for_chat") as mock_menu, \
         patch("codogram.handlers.migration.check_bot_admin_rights", new_callable=AsyncMock) as mock_check:
        mock_pm.get_by_chat.return_value = mock_project
        mock_check.return_value = True  # Bot has admin rights

        await on_chat_migration(message, telegram_queue)

        # Verify chat_id updated
        assert mock_project.chat_id == 222222
        # Verify config saved (at least once for chat_id update)
        assert mock_pm._save.call_count >= 1
        # Verify menu registered (only when bot has admin rights)
        mock_menu.assert_called_once_with(message.bot, 222222, is_forum=True)
        # Verify notification sent
        telegram_queue.enqueue.assert_called_once()
