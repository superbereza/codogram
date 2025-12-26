# tests/test_tmux_selector.py
from telegram_bridge.tmux_selector import create_tmux_selection_keyboard

def test_create_tmux_selection_keyboard():
    keyboard = create_tmux_selection_keyboard(["session1", "session2"], "my-project")

    assert len(keyboard.inline_keyboard) == 2
    assert keyboard.inline_keyboard[0][0].text == "📟 session1"
    assert keyboard.inline_keyboard[0][0].callback_data == "select_tmux:my-project:session1"
    assert keyboard.inline_keyboard[1][0].text == "📟 session2"
    assert keyboard.inline_keyboard[1][0].callback_data == "select_tmux:my-project:session2"


def test_create_tmux_selection_keyboard_single():
    keyboard = create_tmux_selection_keyboard(["only-session"], "test-project")

    assert len(keyboard.inline_keyboard) == 1
    assert keyboard.inline_keyboard[0][0].text == "📟 only-session"
    assert keyboard.inline_keyboard[0][0].callback_data == "select_tmux:test-project:only-session"


def test_create_tmux_selection_keyboard_empty():
    keyboard = create_tmux_selection_keyboard([], "empty-project")

    assert len(keyboard.inline_keyboard) == 0
