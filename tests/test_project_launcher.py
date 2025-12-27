# tests/test_project_launcher.py
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Set env before imports
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from codogram.project_launcher import (
    resolve_project_path,
    ProjectPathResult,
    is_tmux_session_exists,
    create_tmux_with_claude,
    LaunchResult,
)


def test_resolve_path_convention_exists(tmp_path):
    """Use convention path if directory exists."""
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()

    with patch("codogram.project_launcher.settings") as mock_settings:
        mock_settings.base_dir = str(tmp_path)
        result = resolve_project_path("my-project", None)

    assert result.exists
    assert result.path == str(project_dir)


def test_resolve_path_custom_exists(tmp_path):
    """Use custom path if provided and exists."""
    custom_dir = tmp_path / "custom" / "location"
    custom_dir.mkdir(parents=True)

    result = resolve_project_path("my-project", str(custom_dir))

    assert result.exists
    assert result.path == str(custom_dir)


def test_resolve_path_not_exists(tmp_path):
    """Return not exists if directory missing."""
    with patch("codogram.project_launcher.settings") as mock_settings:
        mock_settings.base_dir = str(tmp_path)
        result = resolve_project_path("nonexistent", None)

    assert not result.exists
    assert result.path == str(tmp_path / "nonexistent")


def test_is_tmux_session_exists_false():
    """Return False for non-existent session."""
    result = is_tmux_session_exists("nonexistent-session-12345")
    assert result is False


def test_create_tmux_with_claude(tmp_path):
    """Create tmux session and run claude command."""
    import subprocess

    session_name = f"test-claude-{os.getpid()}"
    project_path = str(tmp_path)

    try:
        result = create_tmux_with_claude(session_name, project_path)
        assert result.success
        assert is_tmux_session_exists(session_name)
    finally:
        # Cleanup
        subprocess.run(["tmux", "kill-session", "-t", session_name],
                      capture_output=True)
