"""Tests for bot validation functions."""
import pytest


def test_is_valid_project_name_valid():
    """Test valid project names."""
    from src.telegram_bridge.bot import is_valid_project_name

    assert is_valid_project_name("my-project") == True
    assert is_valid_project_name("my_project") == True
    assert is_valid_project_name("MyProject123") == True
    assert is_valid_project_name("a") == True


def test_is_valid_project_name_invalid():
    """Test invalid project names."""
    from src.telegram_bridge.bot import is_valid_project_name

    assert is_valid_project_name("") == False
    assert is_valid_project_name("my project") == False  # space
    assert is_valid_project_name("my/project") == False  # slash
    assert is_valid_project_name("../etc") == False  # path traversal
    assert is_valid_project_name("my.project") == False  # dot
