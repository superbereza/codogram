# tests/test_project_state.py
import os
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from telegram_bridge.session_manager import ProjectState


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
        claude_session_id="abc-123",
        jsonl_path="/path/to/jsonl",
    )

    assert project.chat_id == -123
    assert project.tmux_session == "claude-my-project"
    assert project.claude_session_id == "abc-123"
