# tests/test_config_users.py
"""Tests for user storage in config."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_load_config_returns_users_key():
    """Config should always have users key."""
    from codogram.config import load_config

    with patch("codogram.config.CONFIG_PATH") as mock_path:
        mock_path.exists.return_value = False
        config = load_config()

    assert "users" in config
    assert "projects" in config


def test_get_user_onboarded_false_for_new_user():
    """New users should not be onboarded."""
    from codogram.config import get_user_onboarded

    with patch("codogram.config.load_config") as mock_load:
        mock_load.return_value = {"users": {}, "projects": {}}
        result = get_user_onboarded(123456)

    assert result is False


def test_get_user_onboarded_true_for_existing_user():
    """Existing onboarded users should return True."""
    from codogram.config import get_user_onboarded

    with patch("codogram.config.load_config") as mock_load:
        mock_load.return_value = {
            "users": {"123456": {"onboarded": True}},
            "projects": {}
        }
        result = get_user_onboarded(123456)

    assert result is True


def test_set_user_onboarded():
    """Should save onboarded state for user."""
    from codogram.config import set_user_onboarded

    saved_config = None
    def capture_save(config):
        nonlocal saved_config
        saved_config = config

    with patch("codogram.config.load_config") as mock_load, \
         patch("codogram.config.save_config", side_effect=capture_save):
        mock_load.return_value = {"users": {}, "projects": {}}
        set_user_onboarded(123456)

    assert saved_config is not None
    assert "123456" in saved_config["users"]
    assert saved_config["users"]["123456"]["onboarded"] is True
    assert "onboarded_at" in saved_config["users"]["123456"]
