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
    git_clone,
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


def test_git_clone_cleans_up_on_failure(tmp_path):
    """git_clone should remove partial directory on failure."""
    target = tmp_path / "test-repo"

    # Clone from nonexistent GitHub repo - will definitely fail
    result = git_clone(str(target), "https://github.com/nonexistent-user-12345/nonexistent-repo-67890.git")

    assert result.success is False
    # Directory should NOT exist after failed clone
    assert not target.exists(), "Failed clone should clean up directory"


def test_git_clone_cleans_up_partial_directory(tmp_path):
    """git_clone should clean up if directory is left in partial state."""
    target = tmp_path / "test-repo"

    # Mock subprocess.run to simulate a failed clone that leaves partial directory
    def mock_subprocess_run(cmd, **kwargs):
        # Create partial directory to simulate interrupted clone
        target.mkdir(exist_ok=True)
        (target / ".git").mkdir()
        # Return failed result
        result = MagicMock()
        result.returncode = 128
        result.stderr = "fatal: repository not found"
        return result

    with patch("codogram.project_launcher.subprocess.run", side_effect=mock_subprocess_run):
        result = git_clone(str(target), "https://github.com/example/repo.git")

    assert result.success is False
    # Directory should be cleaned up even though git left it
    assert not target.exists(), "Failed clone should clean up partial directory"
