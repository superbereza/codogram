"""Tests for settings keyboard builder."""

import pytest
from codogram.keyboards.settings import settings_keyboard, _short_id


def test_settings_keyboard_structure():
    """Settings keyboard has 4 vertical buttons."""
    kb = settings_keyboard("claude-test")

    # 4 rows, 1 button each
    assert len(kb.inline_keyboard) == 4
    assert len(kb.inline_keyboard[0]) == 1
    assert len(kb.inline_keyboard[1]) == 1
    assert len(kb.inline_keyboard[2]) == 1
    assert len(kb.inline_keyboard[3]) == 1


def test_settings_keyboard_button_labels():
    """Buttons show command names."""
    kb = settings_keyboard("claude-test")

    assert kb.inline_keyboard[0][0].text == "/auto_accept"
    assert kb.inline_keyboard[1][0].text == "/verbose"
    assert kb.inline_keyboard[2][0].text == "/shift_tab"
    assert kb.inline_keyboard[3][0].text == "Close"


def test_settings_keyboard_callback_data():
    """Callback data uses short hash format."""
    kb = settings_keyboard("claude-test")
    sid = _short_id("claude-test")

    assert kb.inline_keyboard[0][0].callback_data == f"set:aa:{sid}"
    assert kb.inline_keyboard[1][0].callback_data == f"set:v:{sid}"
    assert kb.inline_keyboard[2][0].callback_data == f"set:m:{sid}"
    assert kb.inline_keyboard[3][0].callback_data == "set:close"


def test_short_id_length():
    """Short ID is 12 chars for any tmux name."""
    short_name = "claude-test"
    long_name = "claude-codogram-switch-full-short-claude-statuses"

    assert len(_short_id(short_name)) == 12
    assert len(_short_id(long_name)) == 12


def test_short_id_deterministic():
    """Same input produces same short ID."""
    name = "claude-test"
    assert _short_id(name) == _short_id(name)
