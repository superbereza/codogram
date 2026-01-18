# tests/keyboards/test_setup_type.py
from codogram.keyboards.setup.setup_type import (
    setup_type_keyboard,
    admin_check_keyboard,
)


def test_setup_type_keyboard_has_four_buttons():
    """Setup type keyboard has Clone/Connect/New/Cancel buttons."""
    kb = setup_type_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 4

    texts = [btn.text for btn in buttons]
    assert "Clone repository" in texts
    assert "Connect to existing folder" in texts
    assert "Start new project" in texts
    assert "Cancel" in texts


def test_setup_type_keyboard_callback_data():
    """Setup type buttons have correct callback_data."""
    kb = setup_type_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]

    callbacks = [btn.callback_data for btn in buttons]
    assert "setup:clone" in callbacks
    assert "setup:connect" in callbacks
    assert "setup:new" in callbacks
    assert "setup:cancel" in callbacks


def test_admin_check_keyboard():
    """Admin check keyboard has Check rights button."""
    kb = admin_check_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]

    assert len(buttons) == 1
    assert buttons[0].text == "Check rights"
    assert buttons[0].callback_data == "admin:check"
