"""Tests for reset flow keyboards."""
from codogram import strings
from codogram.keyboards.reset import (
    reset_confirm_keyboard,
    reset_dir_choice_keyboard,
    reset_uncommitted_keyboard,
)


def test_reset_confirm_keyboard():
    kb = reset_confirm_keyboard()
    buttons = [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]

    assert (strings.BTN_CONTINUE, "reset:continue") in buttons
    assert (strings.BTN_CANCEL, "reset:cancel") in buttons


def test_reset_dir_choice_keyboard():
    kb = reset_dir_choice_keyboard()
    buttons = [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]

    assert (strings.BTN_KEEP_DIR, "reset:keep") in buttons
    assert (strings.BTN_DELETE_DIR, "reset:delete") in buttons
    assert (strings.BTN_GO_BACK, "reset:back") in buttons


def test_reset_uncommitted_keyboard():
    kb = reset_uncommitted_keyboard()
    buttons = [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]

    assert (strings.BTN_KEEP_DIR, "reset:keep") in buttons
    assert (strings.BTN_DELETE_ANYWAY, "reset:delete") in buttons
    assert (strings.BTN_GO_BACK, "reset:back") in buttons
