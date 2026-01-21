# tests/keyboards/test_git_choice.py
from codogram.telegram.keyboards.setup.git_choice import git_choice_keyboard


def test_git_choice_keyboard_has_all_options():
    """Git choice keyboard has all 4 options."""
    kb = git_choice_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "git:init" in callbacks
    assert "git:gh" in callbacks
    assert "git:clone" in callbacks
    assert "git:none" in callbacks


def test_git_choice_keyboard_has_go_back():
    """Git choice keyboard has go back button."""
    kb = git_choice_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "git:back" in callbacks
