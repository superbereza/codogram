"""Tests for SessionStateService."""
import os
from unittest.mock import Mock, patch

import pytest

# Set env before imports
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from codogram.services.session_state import SessionStateService
from codogram.claude.screen import StatusBar


class TestSessionStateService:
    def test_get_status_returns_status_bar(self):
        """Service should capture pane and parse status bar."""
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True
        mock_tmux.capture_pane.return_value = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏵⏵ accept edits on · 1 background task
"""
        service = SessionStateService()
        result = service.get_status(mock_tmux)

        assert result.success is True
        assert result.status_bar.approval_mode == "accept edits"
        assert result.status_bar.background_tasks == 1

    def test_get_status_tmux_not_exists(self):
        """Service should return error if tmux doesn't exist."""
        mock_tmux = Mock()
        mock_tmux.exists.return_value = False

        service = SessionStateService()
        result = service.get_status(mock_tmux)

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_cycle_mode_sends_shift_tab(self):
        """Service should send BTab and return new mode."""
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True
        # First capture: accept edits (before), second capture: plan mode (after)
        # Must include separator for parse_status_bar to find status lines
        mock_tmux.capture_pane.side_effect = [
            "──────────────────────────────────────────────────────────────────────\n⏵⏵ accept edits on",
            "──────────────────────────────────────────────────────────────────────\n⏸ plan mode on",
        ]

        service = SessionStateService()

        # Patch time.sleep to speed up test
        with patch("codogram.services.session_state.time.sleep"):
            result = service.cycle_approval_mode(mock_tmux)

        mock_tmux.send_key.assert_called_once_with("BTab")
        assert result.success is True
        assert result.new_mode == "plan mode"

    def test_cycle_mode_tmux_not_exists(self):
        """cycle_approval_mode should return error if tmux doesn't exist."""
        mock_tmux = Mock()
        mock_tmux.exists.return_value = False

        service = SessionStateService()
        result = service.cycle_approval_mode(mock_tmux)

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_cycle_mode_returns_old_mode(self):
        """cycle_approval_mode should return old mode in result."""
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True
        mock_tmux.capture_pane.side_effect = [
            "──────────────────────────────────────────────────────────────────────\n⏵⏵ accept edits on",
            "──────────────────────────────────────────────────────────────────────\n⏸ plan mode on",
        ]

        service = SessionStateService()

        with patch("codogram.services.session_state.time.sleep"):
            result = service.cycle_approval_mode(mock_tmux)

        assert result.old_mode == "accept edits"
        assert result.new_mode == "plan mode"

    def test_get_status_with_context_percent(self):
        """Service should parse context percentage from status bar."""
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True
        mock_tmux.capture_pane.return_value = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏵⏵ accept edits on · auto-compact: 45%
"""
        service = SessionStateService()
        result = service.get_status(mock_tmux)

        assert result.success is True
        assert result.status_bar.context_percent == 45
