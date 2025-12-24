import pytest
from telegram_bridge.tmux import TmuxSession

def test_send_escapes_quotes():
    session = TmuxSession("test-session", "/tmp")
    cmd = session._build_send_command("hello 'world'")
    assert "hello" in cmd
    assert "'" in cmd or "\\'" in cmd
