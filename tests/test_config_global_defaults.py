# tests/test_config_global_defaults.py
"""Tests for global defaults in config."""
import json
import pytest
from pathlib import Path


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    """Use temporary directory for config."""
    config_dir = tmp_path / ".codogram"
    config_dir.mkdir()
    config_path = config_dir / "config.json"

    # Patch the module-level constants
    import codogram.config as config_module
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    return config_path


class TestHardcodedDefaults:
    """Tests for HARDCODED_DEFAULTS constant."""

    def test_hardcoded_defaults_exists(self):
        """Verify all 9 keys are present in HARDCODED_DEFAULTS."""
        from codogram.config import HARDCODED_DEFAULTS

        expected_keys = {
            "auto_accept",
            "response_mode",
            "display_mode",
            "line_limit",
            "display_bullet",
            "display_thinking_text",
            "working_status",
            "feat_suggestions",
            "feat_avatar_pack",
        }

        assert set(HARDCODED_DEFAULTS.keys()) == expected_keys
        assert len(HARDCODED_DEFAULTS) == 9


class TestGetGlobalDefaults:
    """Tests for get_global_defaults function."""

    def test_get_global_defaults_returns_hardcoded_when_no_config(self, temp_config_dir):
        """When no config exists, returns HARDCODED_DEFAULTS."""
        from codogram.config import get_global_defaults, HARDCODED_DEFAULTS

        result = get_global_defaults()

        assert result == HARDCODED_DEFAULTS

    def test_get_global_defaults_returns_saved_values(self, temp_config_dir):
        """When config has global_defaults, they override hardcoded."""
        from codogram.config import get_global_defaults, HARDCODED_DEFAULTS

        # Write config with custom global_defaults
        config = {
            "projects": {},
            "users": {},
            "global_defaults": {
                "auto_accept": True,
                "line_limit": 10,
            }
        }
        temp_config_dir.write_text(json.dumps(config))

        result = get_global_defaults()

        # Custom values should override
        assert result["auto_accept"] is True
        assert result["line_limit"] == 10
        # Other values should come from hardcoded
        assert result["response_mode"] == HARDCODED_DEFAULTS["response_mode"]
        assert result["display_mode"] == HARDCODED_DEFAULTS["display_mode"]


class TestSetGlobalDefault:
    """Tests for set_global_default function."""

    def test_set_global_default_creates_key(self, temp_config_dir):
        """Setting a global default creates the key in config."""
        from codogram.config import set_global_default, load_config

        set_global_default("auto_accept", True)

        config = load_config()
        assert "global_defaults" in config
        assert config["global_defaults"]["auto_accept"] is True

    def test_set_global_default_preserves_other_keys(self, temp_config_dir):
        """Setting one key preserves other global_defaults keys."""
        from codogram.config import set_global_default, load_config

        # Set first key
        set_global_default("auto_accept", True)
        # Set second key
        set_global_default("line_limit", 20)

        config = load_config()
        assert config["global_defaults"]["auto_accept"] is True
        assert config["global_defaults"]["line_limit"] == 20
