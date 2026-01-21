# tests/keyboards/test_common.py
"""Tests for common keyboard helpers."""
from codogram.telegram.keyboards.setup.common import go_back_keyboard, clone_error_keyboard
from codogram import strings


def test_go_back_keyboard_has_single_button():
    """Go back keyboard has exactly one button."""
    kb = go_back_keyboard("test:back")
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 1


def test_go_back_keyboard_button_text():
    """Go back button has correct text."""
    kb = go_back_keyboard("test:back")
    button = kb.inline_keyboard[0][0]
    assert button.text == strings.BTN_GO_BACK


def test_go_back_keyboard_callback_data():
    """Go back button has provided callback_data."""
    kb = go_back_keyboard("custom:callback")
    button = kb.inline_keyboard[0][0]
    assert button.callback_data == "custom:callback"


def test_clone_error_keyboard_has_three_buttons():
    """Clone error keyboard has Retry, Change URL, and Go back buttons."""
    kb = clone_error_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 3


def test_clone_error_keyboard_retry_button():
    """Clone error keyboard has Retry button with correct callback."""
    kb = clone_error_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]

    retry_btn = next(btn for btn in buttons if btn.text == strings.BTN_RETRY)
    assert retry_btn.callback_data == "clone:retry"


def test_clone_error_keyboard_change_url_button():
    """Clone error keyboard has Change URL button with correct callback."""
    kb = clone_error_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]

    change_btn = next(btn for btn in buttons if btn.text == strings.BTN_CHANGE_URL)
    assert change_btn.callback_data == "clone:change_url"


def test_clone_error_keyboard_go_back_button():
    """Clone error keyboard has Go back button with correct callback."""
    kb = clone_error_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]

    back_btn = next(btn for btn in buttons if btn.text == strings.BTN_GO_BACK)
    assert back_btn.callback_data == "clone:back"


def test_clone_error_keyboard_layout():
    """Clone error keyboard has correct layout: [Retry][Change URL] on row 1, [Go back] on row 2."""
    kb = clone_error_keyboard()

    assert len(kb.inline_keyboard) == 2
    assert len(kb.inline_keyboard[0]) == 2  # Retry and Change URL
    assert len(kb.inline_keyboard[1]) == 1  # Go back

    assert kb.inline_keyboard[0][0].text == strings.BTN_RETRY
    assert kb.inline_keyboard[0][1].text == strings.BTN_CHANGE_URL
    assert kb.inline_keyboard[1][0].text == strings.BTN_GO_BACK
