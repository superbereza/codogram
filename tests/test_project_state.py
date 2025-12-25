# tests/test_project_state.py
import asyncio
import os
from unittest.mock import AsyncMock

os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from telegram_bridge.session_manager import ProjectState, ProjectManager


def test_project_state_defaults():
    """ProjectState has correct defaults."""
    project = ProjectState(project_name="test-project")

    assert project.project_name == "test-project"
    assert project.chat_id is None
    assert project.cwd is None
    assert project.tmux_session is None
    assert project.claude_session_id is None
    assert project.jsonl_path is None
    assert project.poller_task is None
    assert project.watcher_task is None


def test_project_state_with_values():
    """ProjectState accepts all values."""
    project = ProjectState(
        project_name="my-project",
        chat_id=-123,
        cwd="/home/user/dev/my-project",
        tmux_session="claude-my-project",
        session_id="abc-123",
        jsonl_path="/path/to/jsonl",
    )

    assert project.chat_id == -123
    assert project.tmux_session == "claude-my-project"
    assert project.claude_session_id == "abc-123"  # Test backwards compat property


def test_project_manager_get_or_create():
    """get_or_create creates new project or returns existing."""
    pm = ProjectManager()

    # First call creates
    project1 = pm.get_or_create("test-project")
    assert project1.project_name == "test-project"

    # Second call returns same
    project2 = pm.get_or_create("test-project")
    assert project1 is project2


def test_project_manager_get_by_chat():
    """get_by_chat finds project by chat_id."""
    pm = ProjectManager()

    project = pm.get_or_create("test-project")
    project.chat_id = -123

    found = pm.get_by_chat(-123)
    assert found is project

    not_found = pm.get_by_chat(-999)
    assert not_found is None


def test_project_manager_get_by_session():
    """get_by_session finds project by claude_session_id."""
    pm = ProjectManager()

    project = pm.get_or_create("test-project")
    project.claude_session_id = "abc-123"

    found = pm.get_by_session("abc-123")
    assert found is project

    not_found = pm.get_by_session("xyz")
    assert not_found is None


def test_update_from_telegram():
    """update_from_telegram sets chat_id and cwd."""
    pm = ProjectManager()

    async def run():
        project = await pm.update_from_telegram(
            project_name="test-project",
            chat_id=-123,
            cwd="/home/user/dev/test-project",
            start_poller=AsyncMock(return_value=asyncio.current_task()),
            start_watcher=AsyncMock(return_value=asyncio.current_task()),
        )
        assert project.chat_id == -123
        assert project.cwd == "/home/user/dev/test-project"

    asyncio.run(run())


def test_maybe_start_tasks_needs_both():
    """_maybe_start_tasks needs tmux_session AND chat_id for poller."""
    pm = ProjectManager()

    async def run():
        mock_poller = AsyncMock(return_value=asyncio.current_task())
        mock_watcher = AsyncMock(return_value=asyncio.current_task())

        # Only chat_id - no poller
        project = pm.get_or_create("test")
        project.chat_id = -123
        await pm._maybe_start_tasks(project, mock_poller, mock_watcher)
        mock_poller.assert_not_called()

        # Add tmux_session - poller starts
        project.tmux_session = "claude-test"
        await pm._maybe_start_tasks(project, mock_poller, mock_watcher)
        mock_poller.assert_called_once()

    asyncio.run(run())


def test_update_from_hook():
    """update_from_hook sets Claude-related fields."""
    pm = ProjectManager()

    async def run():
        project = await pm.update_from_hook(
            session_id="abc-123",
            cwd="/home/user/dev/test-project",
            tmux_session="claude-test-project",
            start_poller=AsyncMock(return_value=asyncio.current_task()),
            start_watcher=AsyncMock(return_value=asyncio.current_task()),
        )

        assert project.project_name == "test-project"
        assert project.claude_session_id == "abc-123"
        assert project.tmux_session == "claude-test-project"
        assert project.cwd == "/home/user/dev/test-project"

    asyncio.run(run())


def test_session_end_race_protection():
    """SessionEnd with old session_id is ignored."""
    pm = ProjectManager()

    async def run():
        mock_poller = AsyncMock(return_value=asyncio.current_task())
        mock_watcher = AsyncMock(return_value=asyncio.current_task())

        # Create project with session abc
        project = await pm.update_from_hook(
            session_id="abc",
            cwd="/tmp/test",
            tmux_session="test",
            start_poller=mock_poller,
            start_watcher=mock_watcher,
        )

        # Update to session xyz
        project.claude_session_id = "xyz"

        # SessionEnd for old "abc" should be ignored
        await pm.handle_session_end("abc")

        # Session still has xyz
        assert project.claude_session_id == "xyz"

    asyncio.run(run())
