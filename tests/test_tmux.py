import pytest
from unittest.mock import MagicMock, patch
from telegram_bridge.tmux import TmuxSession, find_all_tmux_by_cwd, find_tmux_by_convention

def test_find_all_tmux_by_cwd_single():
    # Mock subprocess to return one matching session
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="claude-project /home/user/project\n"
        )

        result = find_all_tmux_by_cwd("/home/user/project")
        assert result == ["claude-project"]

def test_find_all_tmux_by_cwd_multiple():
    # Mock subprocess to return multiple sessions
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="claude-1 /home/user/project\nother /other/path\nclaude-2 /home/user/project\n"
        )

        result = find_all_tmux_by_cwd("/home/user/project")
        assert sorted(result) == ["claude-1", "claude-2"]

def test_find_all_tmux_by_cwd_not_found():
    # Mock subprocess to return no matching sessions
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="other /other/path\n"
        )

        result = find_all_tmux_by_cwd("/home/user/project")
        assert result == []

def test_find_tmux_by_convention_found():
    # Mock TmuxSession.exists() to return True
    with patch('telegram_bridge.tmux.TmuxSession.exists', return_value=True):
        result = find_tmux_by_convention("my-project")
        assert result == "claude-my-project"

def test_find_tmux_by_convention_fallback():
    # Mock first pattern not found, second found
    with patch('telegram_bridge.tmux.TmuxSession.exists') as mock_exists:
        mock_exists.side_effect = [False, True]

        result = find_tmux_by_convention("my-project")
        assert result == "my-project"

def test_find_tmux_by_convention_not_found():
    with patch('telegram_bridge.tmux.TmuxSession.exists', return_value=False):
        result = find_tmux_by_convention("my-project")
        assert result is None
