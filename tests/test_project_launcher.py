# tests/test_project_launcher.py
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Set env before imports
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from telegram_bridge.project_launcher import resolve_project_path, ProjectPathResult


def test_resolve_path_convention_exists(tmp_path):
    """Use convention path if directory exists."""
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()

    with patch("telegram_bridge.project_launcher.settings") as mock_settings:
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
    with patch("telegram_bridge.project_launcher.settings") as mock_settings:
        mock_settings.base_dir = str(tmp_path)
        result = resolve_project_path("nonexistent", None)

    assert not result.exists
    assert result.path == str(tmp_path / "nonexistent")
