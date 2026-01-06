# tests/test_session_manager.py
import os
# Set env vars BEFORE importing codogram modules
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

    with patch('codogram.session_manager.find_session_for_project', return_value="new-session-123"), \
         patch('codogram.session_manager.compute_jsonl_path', return_value=jsonl_file):

        from codogram.session_manager import ProjectManager, ProjectState
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
    with patch('codogram.session_manager.find_session_for_project', return_value="same-session"):

        from codogram.session_manager import ProjectManager, ProjectState
        manager = ProjectManager()
        project = ProjectState(project_name="test", cwd="/test/path", chat_id=123)
        project.session_id = "same-session"
        manager.projects["test"] = project

        changed = manager.refresh_project_session(project)

        assert changed is False
        assert project.session_id == "same-session"

def test_refresh_project_session_no_cwd():
    """refresh_project_session should handle missing cwd."""
    from codogram.session_manager import ProjectManager, ProjectState
    manager = ProjectManager()
    project = ProjectState(project_name="test", cwd=None, chat_id=123)
    manager.projects["test"] = project

    changed = manager.refresh_project_session(project)

    assert changed is False

def test_refresh_project_session_jsonl_not_exists(tmp_path):
    """refresh_project_session should handle non-existent jsonl."""
    with patch('codogram.session_manager.find_session_for_project', return_value="new-session"), \
         patch('codogram.session_manager.compute_jsonl_path', return_value=tmp_path / "nonexistent.jsonl"):

        from codogram.session_manager import ProjectManager, ProjectState
        manager = ProjectManager()
        project = ProjectState(project_name="test", cwd="/test/path", chat_id=123)
        manager.projects["test"] = project

        changed = manager.refresh_project_session(project)

        assert changed is True
        assert project.session_id == "new-session"
        assert project.jsonl_path is None  # File doesn't exist


# Tests for ThreadInfo
def test_thread_info_creation():
    from codogram.session_manager import ThreadInfo
    thread = ThreadInfo(thread_id=12345, name="mystic")
    assert thread.thread_id == 12345
    assert thread.name == "mystic"
    assert thread.session_id is None
    assert thread.jsonl_path is None


def test_thread_info_get_tmux_session_main():
    from codogram.session_manager import ThreadInfo
    thread = ThreadInfo(thread_id=None, name="main")
    assert thread.get_tmux_session("codogram") == "claude-codogram"


def test_thread_info_get_tmux_session_named():
    from codogram.session_manager import ThreadInfo
    thread = ThreadInfo(thread_id=12345, name="mystic")
    assert thread.get_tmux_session("codogram") == "claude-codogram-mystic"


# Tests for ProjectState.threads
def test_project_state_has_threads():
    from codogram.session_manager import ProjectState, ThreadInfo
    project = ProjectState(project_name="test")
    assert hasattr(project, 'threads')
    assert project.threads == {}


def test_project_state_get_thread():
    from codogram.session_manager import ProjectState, ThreadInfo
    project = ProjectState(project_name="test")
    thread = ThreadInfo(thread_id=None, name="main")
    project.threads[None] = thread
    assert project.get_thread(None) == thread
    assert project.get_thread(12345) is None


def test_project_state_get_or_create_thread():
    from codogram.session_manager import ProjectState
    project = ProjectState(project_name="test")
    thread = project.get_or_create_thread(None, "main")
    assert thread.name == "main"
    assert project.threads[None] == thread
    # Second call returns same thread
    thread2 = project.get_or_create_thread(None, "main")
    assert thread2 is thread


# Tests for config save/load with threads
def test_config_saves_threads(tmp_path, monkeypatch):
    from codogram.session_manager import ProjectManager, ThreadInfo
    from codogram import config

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
    from codogram import config
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

    from codogram.session_manager import ProjectManager
    manager = ProjectManager()
    project = manager.projects.get("test-project")
    assert project is not None
    assert None in project.threads
    assert project.threads[None].name == "main"
    assert 12345 in project.threads
    assert project.threads[12345].name == "mystic"


# Tests for start_requested_at field
def test_thread_info_start_requested_at_default():
    """Test start_requested_at defaults to None."""
    from codogram.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=123, name="test")
    assert thread.start_requested_at is None


def test_thread_info_start_requested_at_assignment():
    """Test start_requested_at can be set."""
    from codogram.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=123, name="test")
    thread.start_requested_at = 1703847600.123
    assert thread.start_requested_at == 1703847600.123


def test_start_requested_at_persistence(tmp_path, monkeypatch):
    """Test start_requested_at survives save/load cycle."""
    from codogram.session_manager import ProjectManager, ThreadInfo
    from codogram import config

    # Use temp config file
    config_file = tmp_path / ".config.json"
    monkeypatch.setattr(config, 'CONFIG_PATH', config_file)

    # Create manager and add project with thread
    pm = ProjectManager()
    project = pm.get_or_create("test-project")
    project.chat_id = 12345
    project.cwd = "/test/path"

    thread = project.get_or_create_thread(100, "test-thread")
    thread.start_requested_at = 1703847600.5
    thread.awaiting_new_session = True

    pm._save()

    # Create new manager (simulates restart)
    pm2 = ProjectManager()
    project2 = pm2.projects.get("test-project")
    thread2 = project2.threads.get(100)

    assert thread2.start_requested_at == 1703847600.5
    assert thread2.awaiting_new_session is True


# Tests for worktree fields
def test_thread_info_has_worktree_fields():
    from codogram.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=123, name="auth")
    assert thread.worktree_path is None
    assert thread.base_branch is None
    assert thread.archived is False

    thread_with_worktree = ThreadInfo(
        thread_id=456,
        name="feature",
        worktree_path="/dev/project-feature",
        base_branch="main",
        archived=True
    )
    assert thread_with_worktree.worktree_path == "/dev/project-feature"
    assert thread_with_worktree.base_branch == "main"
    assert thread_with_worktree.archived is True


def test_worktree_fields_persist_to_config(tmp_path, monkeypatch):
    """Test worktree fields are saved to config file."""
    import json
    from codogram import config
    from codogram.session_manager import ProjectManager, ThreadInfo

    config_file = tmp_path / ".config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", config_file)

    pm = ProjectManager()
    project = pm.get_or_create("test-project")
    project.chat_id = 123
    project.cwd = "/dev/test-project"

    thread = project.get_or_create_thread(456, "auth")
    thread.worktree_path = "/dev/test-project-auth"
    thread.base_branch = "main"
    thread.archived = True

    pm._save()

    saved = json.loads(config_file.read_text())
    thread_data = saved["projects"]["test-project"]["threads"]["456"]
    assert thread_data["worktree_path"] == "/dev/test-project-auth"
    assert thread_data["base_branch"] == "main"
    assert thread_data["archived"] is True


def test_worktree_fields_load_from_config(tmp_path, monkeypatch):
    """Test worktree fields are loaded from config file."""
    import json
    from codogram import config

    config_data = {
        "projects": {
            "test-project": {
                "chat_id": 123,
                "cwd": "/dev/test-project",
                "threads": {
                    "456": {
                        "name": "auth",
                        "worktree_path": "/dev/test-project-auth",
                        "base_branch": "main",
                        "archived": True
                    }
                }
            }
        }
    }

    config_file = tmp_path / ".config.json"
    config_file.write_text(json.dumps(config_data))
    monkeypatch.setattr(config, "CONFIG_PATH", config_file)

    from codogram.session_manager import ProjectManager
    pm = ProjectManager()
    project = pm.projects.get("test-project")
    thread = project.get_thread(456)

    assert thread.worktree_path == "/dev/test-project-auth"
    assert thread.base_branch == "main"
    assert thread.archived is True


def test_thread_has_valid_session():
    """ThreadInfo.has_valid_session checks jsonl exists."""
    from codogram.session_manager import ThreadInfo
    from pathlib import Path
    import tempfile
    import os

    # No session_id
    thread = ThreadInfo(name="test", thread_id=123)
    assert thread.has_valid_session() is False

    # session_id but no jsonl_path
    thread.session_id = "abc-123"
    assert thread.has_valid_session() is False

    # session_id and jsonl_path but file doesn't exist
    thread.jsonl_path = "/nonexistent/path.jsonl"
    assert thread.has_valid_session() is False

    # session_id and jsonl_path and file exists
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        try:
            thread.jsonl_path = f.name
            assert thread.has_valid_session() is True
        finally:
            os.unlink(f.name)
