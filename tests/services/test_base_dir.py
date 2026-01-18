# tests/services/test_base_dir.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from codogram.services.setup.base_dir import check_base_dir


def test_check_base_dir_returns_none_when_not_configured():
    """Returns None when base_dir is not set."""
    mock_settings = MagicMock()
    mock_settings.base_dir = None

    with patch("codogram.services.setup.base_dir.settings", mock_settings):
        result = check_base_dir()
        assert result is None


def test_check_base_dir_returns_none_when_empty_string():
    """Returns None when base_dir is empty string."""
    mock_settings = MagicMock()
    mock_settings.base_dir = ""

    with patch("codogram.services.setup.base_dir.settings", mock_settings):
        result = check_base_dir()
        assert result is None


def test_check_base_dir_returns_none_when_dir_not_exists():
    """Returns None when base_dir doesn't exist."""
    mock_settings = MagicMock()
    mock_settings.base_dir = "/nonexistent/path/12345"

    with patch("codogram.services.setup.base_dir.settings", mock_settings):
        result = check_base_dir()
        assert result is None


def test_check_base_dir_returns_path_when_valid(tmp_path):
    """Returns Path when base_dir exists."""
    mock_settings = MagicMock()
    mock_settings.base_dir = str(tmp_path)

    with patch("codogram.services.setup.base_dir.settings", mock_settings):
        result = check_base_dir()
        assert result == tmp_path


def test_check_base_dir_expands_user_tilde(tmp_path, monkeypatch):
    """Expands ~ in base_dir path."""
    mock_settings = MagicMock()
    mock_settings.base_dir = "~/test_dir"

    # Make expanduser return tmp_path
    monkeypatch.setattr(Path, "expanduser", lambda self: tmp_path)

    with patch("codogram.services.setup.base_dir.settings", mock_settings):
        result = check_base_dir()
        assert result == tmp_path
