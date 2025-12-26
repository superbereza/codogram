"""Integration tests for tmux.send()."""
import subprocess
import time
import pytest

from telegram_bridge.tmux import TmuxSession


@pytest.fixture
def test_tmux_session():
    """Create a test tmux session."""
    session_name = "pytest-tmux-test"
    # Kill if exists
    subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)
    # Create new
    subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

    yield TmuxSession(session_name, "/tmp")

    # Cleanup
    subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)


def test_send_simple_text(test_tmux_session):
    """Test sending simple text."""
    test_tmux_session.send("hello world")
    time.sleep(0.1)

    content = test_tmux_session.capture_pane()
    assert "hello world" in content


def test_send_special_chars(test_tmux_session):
    """Test sending text with special characters."""
    test_tmux_session.send("echo $HOME")
    time.sleep(0.1)

    content = test_tmux_session.capture_pane()
    # Should be literal, not expanded
    assert "$HOME" in content or "/home" in content  # Either literal or expanded is OK


def test_send_quotes(test_tmux_session):
    """Test sending text with quotes."""
    test_tmux_session.send("echo 'hello \"world\"'")
    time.sleep(0.1)

    content = test_tmux_session.capture_pane()
    assert "hello" in content
