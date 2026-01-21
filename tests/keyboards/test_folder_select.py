# tests/keyboards/test_folder_select.py
import pytest
from codogram.telegram.keyboards.setup.folder_select import (
    folder_select_keyboard,
    FOLDERS_PER_PAGE,
)


def test_folder_select_keyboard_shows_folders():
    """Keyboard shows folder buttons."""
    folders = ["alpha", "beta", "gamma"]
    kb = folder_select_keyboard(folders, page=0, total_pages=1)

    # Flatten buttons
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    texts = [btn.text for btn in buttons]

    assert "alpha" in texts
    assert "beta" in texts
    assert "gamma" in texts


def test_folder_select_keyboard_callback_data():
    """Folder buttons have correct callback_data."""
    folders = ["my-project"]
    kb = folder_select_keyboard(folders, page=0, total_pages=1)

    buttons = [btn for row in kb.inline_keyboard for btn in row]
    folder_btn = next(b for b in buttons if b.text == "my-project")

    assert folder_btn.callback_data == "folder:select:my-project"


def test_folder_select_keyboard_pagination():
    """Pagination buttons appear when needed."""
    folders = ["project"]
    kb = folder_select_keyboard(folders, page=1, total_pages=3)

    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "folder:page:0" in callbacks  # prev
    assert "folder:page:2" in callbacks  # next


def test_folder_select_keyboard_no_prev_on_first_page():
    """No prev button on first page."""
    folders = ["project"]
    kb = folder_select_keyboard(folders, page=0, total_pages=2)

    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "folder:page:-1" not in callbacks
    assert "folder:page:1" in callbacks


def test_folder_select_keyboard_has_view_connected():
    """View connected button present."""
    folders = ["project"]
    kb = folder_select_keyboard(folders, page=0, total_pages=1)

    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "folder:view_connected" in callbacks


def test_folder_select_keyboard_has_go_back():
    """Go back button present."""
    folders = ["project"]
    kb = folder_select_keyboard(folders, page=0, total_pages=1)

    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "folder:back" in callbacks
