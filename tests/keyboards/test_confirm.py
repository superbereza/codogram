# tests/keyboards/test_confirm.py
from codogram.keyboards.setup.confirm import rename_confirm_keyboard
from codogram.keyboards.setup.common import folder_exists_keyboard


def test_rename_confirm_keyboard():
    """Rename confirm has Yes/No buttons."""
    kb = rename_confirm_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "rename:yes" in callbacks
    assert "rename:no" in callbacks


def test_folder_exists_keyboard():
    """Folder exists has Use existing / Different name."""
    kb = folder_exists_keyboard("clone")
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "exists:use" in callbacks
    assert "exists:rename" in callbacks
    assert "clone:back" in callbacks
