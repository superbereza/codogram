"""Tests for create flow keyboard."""
import os
# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from codogram.keyboards.create_flow import (
    build_name_prompt_keyboard,
    CALLBACK_MAGIC_PREFIX,
    CALLBACK_CANCEL,
)
from codogram.domain.create_flow import CreateType


def test_keyboard_branch_buttons():
    kb = build_name_prompt_keyboard(CreateType.BRANCH)
    buttons = kb.inline_keyboard

    assert len(buttons) == 2
    assert buttons[0][0].text == "🔮 Magic name"
    assert buttons[0][0].callback_data == f"{CALLBACK_MAGIC_PREFIX}branch"
    assert buttons[1][0].text == "[<<] Go back"
    assert buttons[1][0].callback_data == CALLBACK_CANCEL


def test_keyboard_thread_buttons():
    kb = build_name_prompt_keyboard(CreateType.THREAD)
    buttons = kb.inline_keyboard

    assert buttons[0][0].callback_data == f"{CALLBACK_MAGIC_PREFIX}thread"


def test_callback_constants():
    """Callback data constants are defined."""
    assert CALLBACK_MAGIC_PREFIX == "create_magic:"
    assert CALLBACK_CANCEL == "create_cancel"
