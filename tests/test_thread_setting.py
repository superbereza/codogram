"""Tests for get_thread_setting helper."""
import pytest


def test_get_thread_setting_returns_thread_value_when_set():
    """Thread override takes precedence over global."""
    from codogram.core.session_manager import ThreadInfo, get_thread_setting

    thread = ThreadInfo(thread_id=None, name="test")
    thread.auto_accept = True  # Explicit override

    # Even if global is False, thread value wins
    result = get_thread_setting(thread, "auto_accept", {"auto_accept": False})
    assert result is True


def test_get_thread_setting_returns_global_when_thread_none():
    """Returns global default when thread value is None."""
    from codogram.core.session_manager import ThreadInfo, get_thread_setting

    thread = ThreadInfo(thread_id=None, name="test")
    thread.auto_accept = None  # Not set

    result = get_thread_setting(thread, "auto_accept", {"auto_accept": True})
    assert result is True


def test_get_thread_setting_handles_all_settings():
    """All setting keys work correctly when thread value is None."""
    from codogram.core.session_manager import ThreadInfo, get_thread_setting

    thread = ThreadInfo(thread_id=None, name="test")
    # Set all settings to None to test inheritance
    thread.auto_accept = None
    thread.response_mode = None
    thread.display_mode = None
    thread.line_limit = None
    thread.display_bullet = None
    thread.display_thinking_text = None
    thread.working_status = None

    defaults = {
        "auto_accept": True,
        "response_mode": "polite",
        "display_mode": "headers",
        "line_limit": 10,
        "display_bullet": False,
        "display_thinking_text": True,
        "working_status": True,
    }

    for key, expected in defaults.items():
        result = get_thread_setting(thread, key, defaults)
        assert result == expected, f"Failed for {key}"
