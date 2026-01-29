"""Tests for DM onboarding validation service."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_check_base_dir_configured_returns_error_when_empty():
    """Should return error when BASE_DIR is empty."""
    from codogram.services.dm_onboarding.validation import check_base_dir_configured

    with patch("codogram.services.dm_onboarding.validation.settings") as mock_settings:
        mock_settings.base_dir = ""
        result = check_base_dir_configured()

    assert result.ok is False
    assert "BASE_DIR" in result.message


def test_check_base_dir_configured_returns_ok():
    """Should return ok when BASE_DIR is set."""
    from codogram.services.dm_onboarding.validation import check_base_dir_configured

    with patch("codogram.services.dm_onboarding.validation.settings") as mock_settings:
        mock_settings.base_dir = "/home/user/dev"
        result = check_base_dir_configured()

    assert result.ok is True


def test_check_base_dir_exists_returns_error_when_missing():
    """Should return error when BASE_DIR path doesn't exist."""
    from codogram.services.dm_onboarding.validation import check_base_dir_exists

    with patch("codogram.services.dm_onboarding.validation.settings") as mock_settings, \
         patch("codogram.services.dm_onboarding.validation.Path") as mock_path:
        mock_settings.base_dir = "/nonexistent/path"
        mock_path.return_value.exists.return_value = False
        result = check_base_dir_exists()

    assert result.ok is False


def test_check_binary_available_returns_ok_when_found():
    """Should return ok when binary is in PATH."""
    from codogram.services.dm_onboarding.validation import check_binary_available

    with patch("shutil.which", return_value="/usr/bin/claude"):
        result = check_binary_available("claude")

    assert result.ok is True


def test_check_binary_available_returns_error_when_missing():
    """Should return error when binary is not in PATH."""
    from codogram.services.dm_onboarding.validation import check_binary_available

    with patch("shutil.which", return_value=None):
        result = check_binary_available("claude")

    assert result.ok is False
    assert "claude" in result.message


def test_run_critical_checks_returns_all_errors():
    """Should return all critical check results."""
    from codogram.services.dm_onboarding.validation import run_critical_checks

    with patch("codogram.services.dm_onboarding.validation.settings") as mock_settings, \
         patch("codogram.services.dm_onboarding.validation.Path") as mock_path, \
         patch("shutil.which", return_value="/usr/bin/test"):
        mock_settings.base_dir = "/home/user/dev"
        mock_path.return_value.exists.return_value = True

        results = run_critical_checks()

    assert len(results) == 4  # base_dir configured, exists, claude, tmux
    assert all(r.ok for r in results)
