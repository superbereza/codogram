"""Tests for settings keyboard builder."""

import pytest
from codogram.keyboards.settings import settings_keyboard


def test_settings_keyboard_structure():
    """Settings keyboard has 3 vertical buttons."""
    kb = settings_keyboard("claude-test")

    # 3 rows, 1 button each
    assert len(kb.inline_keyboard) == 3
    assert len(kb.inline_keyboard[0]) == 1
    assert len(kb.inline_keyboard[1]) == 1
    assert len(kb.inline_keyboard[2]) == 1


def test_settings_keyboard_button_labels():
    """Buttons show command names."""
    kb = settings_keyboard("claude-test")

    assert kb.inline_keyboard[0][0].text == "/auto_accept"
    assert kb.inline_keyboard[1][0].text == "/verbose"
    assert kb.inline_keyboard[2][0].text == "/shift_tab"


def test_settings_keyboard_callback_data():
    """Callback data includes tmux session name."""
    kb = settings_keyboard("claude-test")

    assert kb.inline_keyboard[0][0].callback_data == "settings:auto_accept:claude-test"
    assert kb.inline_keyboard[1][0].callback_data == "settings:verbose:claude-test"
    assert kb.inline_keyboard[2][0].callback_data == "settings:mode:claude-test"
