# tests/test_migration_handler.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from codogram.handlers.migration import router, on_chat_migration, MIGRATION_MESSAGE


def test_router_exists():
    """Migration router should exist."""
    assert router is not None
    assert router.name == "migration"


def test_migration_message_format():
    """Migration message follows tone-of-voice."""
    assert "`[v]` Topics enabled" in MIGRATION_MESSAGE
    assert "/thread" in MIGRATION_MESSAGE
    assert "/branch" in MIGRATION_MESSAGE
    assert "/finish" in MIGRATION_MESSAGE


@pytest.mark.asyncio
async def test_migration_ignores_unknown_chat():
    """Migration handler ignores chats without registered project."""
    from codogram.session_manager import project_manager

    message = MagicMock()
    message.chat.id = 999999
    message.migrate_to_chat_id = 888888

    telegram_queue = AsyncMock()

    with patch.object(project_manager, 'get_by_chat', return_value=None):
        await on_chat_migration(message, telegram_queue)

    # Should not send any message
    telegram_queue.enqueue.assert_not_called()
