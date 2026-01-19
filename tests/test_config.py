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


class TestAllowedGroups:
    """Tests for allowed_groups config functions."""

    def test_get_allowed_groups_empty_default(self, tmp_path, monkeypatch):
        """Returns empty set when no allowed_groups in config."""
        monkeypatch.setattr("codogram.config.CONFIG_PATH", tmp_path / "config.json")
        from codogram.config import get_allowed_groups
        assert get_allowed_groups() == set()

    def test_get_allowed_groups_returns_set(self, tmp_path, monkeypatch):
        """Returns set of group IDs from config."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"allowed_groups": [123, 456]}')
        monkeypatch.setattr("codogram.config.CONFIG_PATH", config_path)
        from codogram.config import get_allowed_groups
        assert get_allowed_groups() == {123, 456}

    def test_add_allowed_group(self, tmp_path, monkeypatch):
        """Adds group to allowed list."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"projects": {}}')
        monkeypatch.setattr("codogram.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("codogram.config.CONFIG_DIR", tmp_path)
        from codogram.config import add_allowed_group, get_allowed_groups
        add_allowed_group(123)
        assert 123 in get_allowed_groups()

    def test_add_allowed_group_idempotent(self, tmp_path, monkeypatch):
        """Adding same group twice doesn't duplicate."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"allowed_groups": [123]}')
        monkeypatch.setattr("codogram.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("codogram.config.CONFIG_DIR", tmp_path)
        from codogram.config import add_allowed_group, get_allowed_groups
        add_allowed_group(123)
        assert get_allowed_groups() == {123}

    def test_remove_allowed_group(self, tmp_path, monkeypatch):
        """Removes group from allowed list."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"allowed_groups": [123, 456]}')
        monkeypatch.setattr("codogram.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("codogram.config.CONFIG_DIR", tmp_path)
        from codogram.config import remove_allowed_group, get_allowed_groups
        remove_allowed_group(123)
        assert get_allowed_groups() == {456}

    def test_remove_allowed_group_not_exists(self, tmp_path, monkeypatch):
        """Removing non-existent group is no-op."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"allowed_groups": [456]}')
        monkeypatch.setattr("codogram.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("codogram.config.CONFIG_DIR", tmp_path)
        from codogram.config import remove_allowed_group, get_allowed_groups
        remove_allowed_group(123)  # Should not raise
        assert get_allowed_groups() == {456}
