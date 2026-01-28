"""Tests for ThreadInfo optional fields."""


def test_threadinfo_settings_default_to_none():
    """New ThreadInfo has None for all settings (inherits from global)."""
    from codogram.core.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=None, name="test")

    assert thread.auto_accept is None
    assert thread.response_mode is None
    assert thread.display_mode is None
    assert thread.line_limit is None
    assert thread.display_bullet is None
    assert thread.display_thinking_text is None
    assert thread.working_status is None
    assert thread.feat_suggestions is None
    assert thread.feat_avatar_pack is None


def test_threadinfo_accepts_explicit_values():
    """ThreadInfo can have explicit values set."""
    from codogram.core.session_manager import ThreadInfo

    thread = ThreadInfo(
        thread_id=None,
        name="test",
        auto_accept=True,
        display_mode="headers",
    )

    assert thread.auto_accept is True
    assert thread.display_mode == "headers"
