# tests/test_session_manager.py
import os
# Set env vars BEFORE importing telegram_bridge modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import patch

# Tests for ProjectManager.refresh_project_session
def test_refresh_project_session_changes(tmp_path):
    """refresh_project_session should detect session changes."""
    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.touch()

    with patch('telegram_bridge.session_manager.find_session_for_project', return_value="new-session-123"), \
         patch('telegram_bridge.session_manager.compute_jsonl_path', return_value=jsonl_file):

        from telegram_bridge.session_manager import ProjectManager, ProjectState
        manager = ProjectManager()
        project = ProjectState(project_name="test", cwd="/test/path", chat_id=123)
        project.session_id = "old-session"
        manager.projects["test"] = project

        changed = manager.refresh_project_session(project)

        assert changed is True
        assert project.session_id == "new-session-123"
        assert project.jsonl_path == str(jsonl_file)

def test_refresh_project_session_no_change():
    """refresh_project_session should return False when session unchanged."""
    with patch('telegram_bridge.session_manager.find_session_for_project', return_value="same-session"):

        from telegram_bridge.session_manager import ProjectManager, ProjectState
        manager = ProjectManager()
        project = ProjectState(project_name="test", cwd="/test/path", chat_id=123)
        project.session_id = "same-session"
        manager.projects["test"] = project

        changed = manager.refresh_project_session(project)

        assert changed is False
        assert project.session_id == "same-session"

def test_refresh_project_session_no_cwd():
    """refresh_project_session should handle missing cwd."""
    from telegram_bridge.session_manager import ProjectManager, ProjectState
    manager = ProjectManager()
    project = ProjectState(project_name="test", cwd=None, chat_id=123)
    manager.projects["test"] = project

    changed = manager.refresh_project_session(project)

    assert changed is False

def test_refresh_project_session_jsonl_not_exists(tmp_path):
    """refresh_project_session should handle non-existent jsonl."""
    with patch('telegram_bridge.session_manager.find_session_for_project', return_value="new-session"), \
         patch('telegram_bridge.session_manager.compute_jsonl_path', return_value=tmp_path / "nonexistent.jsonl"):

        from telegram_bridge.session_manager import ProjectManager, ProjectState
        manager = ProjectManager()
        project = ProjectState(project_name="test", cwd="/test/path", chat_id=123)
        manager.projects["test"] = project

        changed = manager.refresh_project_session(project)

        assert changed is True
        assert project.session_id == "new-session"
        assert project.jsonl_path is None  # File doesn't exist


# Tests for ThreadInfo
def test_thread_info_creation():
    from telegram_bridge.session_manager import ThreadInfo
    thread = ThreadInfo(thread_id=12345, name="mystic")
    assert thread.thread_id == 12345
    assert thread.name == "mystic"
    assert thread.session_id is None
    assert thread.jsonl_path is None


def test_thread_info_get_tmux_session_main():
    from telegram_bridge.session_manager import ThreadInfo
    thread = ThreadInfo(thread_id=None, name="main")
    assert thread.get_tmux_session("codogram") == "claude-codogram"


def test_thread_info_get_tmux_session_named():
    from telegram_bridge.session_manager import ThreadInfo
    thread = ThreadInfo(thread_id=12345, name="mystic")
    assert thread.get_tmux_session("codogram") == "claude-codogram-mystic"


# Tests for ProjectState.threads
def test_project_state_has_threads():
    from telegram_bridge.session_manager import ProjectState, ThreadInfo
    project = ProjectState(project_name="test")
    assert hasattr(project, 'threads')
    assert project.threads == {}


def test_project_state_get_thread():
    from telegram_bridge.session_manager import ProjectState, ThreadInfo
    project = ProjectState(project_name="test")
    thread = ThreadInfo(thread_id=None, name="main")
    project.threads[None] = thread
    assert project.get_thread(None) == thread
    assert project.get_thread(12345) is None


def test_project_state_get_or_create_thread():
    from telegram_bridge.session_manager import ProjectState
    project = ProjectState(project_name="test")
    thread = project.get_or_create_thread(None, "main")
    assert thread.name == "main"
    assert project.threads[None] == thread
    # Second call returns same thread
    thread2 = project.get_or_create_thread(None, "main")
    assert thread2 is thread


# Tests for config save/load with threads
def test_config_saves_threads(tmp_path, monkeypatch):
    from telegram_bridge.session_manager import ProjectManager, ThreadInfo
    from telegram_bridge import config

    config_file = tmp_path / ".config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", config_file)

    manager = ProjectManager()
    project = manager.get_or_create("test-project")
    project.chat_id = 123
    project.cwd = "/test/path"
    project.threads[None] = ThreadInfo(thread_id=None, name="main")
    project.threads[12345] = ThreadInfo(thread_id=12345, name="mystic")
    manager._save()

    # Reload and check
    import json
    saved = json.loads(config_file.read_text())
    assert "test-project" in saved["projects"]
    assert "threads" in saved["projects"]["test-project"]
    assert "null" in saved["projects"]["test-project"]["threads"]
    assert saved["projects"]["test-project"]["threads"]["null"]["name"] == "main"
    assert "12345" in saved["projects"]["test-project"]["threads"]


def test_config_loads_threads(tmp_path, monkeypatch):
    from telegram_bridge import config
    import json

    config_file = tmp_path / ".config.json"
    config_file.write_text(json.dumps({
        "projects": {
            "test-project": {
                "chat_id": 123,
                "cwd": "/test/path",
                "threads": {
                    "null": {"name": "main"},
                    "12345": {"name": "mystic"}
                }
            }
        }
    }))
    monkeypatch.setattr(config, "CONFIG_PATH", config_file)

    from telegram_bridge.session_manager import ProjectManager
    manager = ProjectManager()
    project = manager.projects.get("test-project")
    assert project is not None
    assert None in project.threads
    assert project.threads[None].name == "main"
    assert 12345 in project.threads
    assert project.threads[12345].name == "mystic"
