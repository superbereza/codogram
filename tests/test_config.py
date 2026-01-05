# tests/test_config.py
"""Tests for config module."""
from codogram.config import Settings


def test_settings_has_timing_constants():
    """Settings should have timing constants with defaults."""
    s = Settings(
        telegram_token="test",
        admin_ids="123",
        base_dir="/tmp"
    )

    assert s.permission_poller_debounce == 0.5
    assert s.permission_poller_interval == 0.5
    assert s.history_watcher_interval == 15
    assert s.session_binding_timeout == 300
    assert s.session_binding_interval == 0.5
    assert s.jsonl_watcher_interval == 0.5
    assert s.claude_launch_timeout == 120
    assert s.project_cleanup_days == 30
