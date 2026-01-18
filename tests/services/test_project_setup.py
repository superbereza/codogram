# tests/services/test_project_setup.py
"""Tests for project setup service.

Note: These tests mock internal functions to avoid loading the full app config.
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass


def test_create_session_name():
    """Test session name generation."""
    from codogram.services.setup.project_setup import create_session_name

    assert create_session_name("my-project") == "claude-my-project"
    assert create_session_name("test") == "claude-test"


@pytest.mark.asyncio
async def test_create_tmux_session_success():
    """Test tmux session creation succeeds."""
    from codogram.services.setup.project_setup import create_tmux_session

    with patch("codogram.services.setup.project_setup.TmuxSession") as mock_cls:
        mock_session = MagicMock()
        mock_session.exists.return_value = True
        mock_cls.return_value = mock_session

        result = await create_tmux_session("test-session", "/tmp/test")

        assert result is True
        mock_session.create.assert_called_once()


@pytest.mark.asyncio
async def test_create_tmux_session_failure():
    """Test tmux session creation fails gracefully."""
    from codogram.services.setup.project_setup import create_tmux_session

    with patch("codogram.services.setup.project_setup.TmuxSession") as mock_cls:
        mock_cls.side_effect = Exception("tmux error")

        result = await create_tmux_session("test-session", "/tmp/test")

        assert result is False


def test_setup_result_dataclass():
    """Test SetupResult dataclass."""
    from codogram.services.setup.project_setup import SetupResult

    # Success case
    result = SetupResult(success=True, tmux_name="claude-test")
    assert result.success is True
    assert result.tmux_name == "claude-test"
    assert result.error is None

    # Failure case
    result = SetupResult(success=False, error="Something went wrong")
    assert result.success is False
    assert result.error == "Something went wrong"
