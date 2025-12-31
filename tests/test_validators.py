"""Tests for domain validators."""
import pytest

from codogram.domain.validators import is_valid_project_name


class TestIsValidProjectName:
    """Tests for is_valid_project_name validator."""

    def test_valid_alphanumeric(self):
        assert is_valid_project_name("myproject") is True

    def test_valid_with_dash(self):
        assert is_valid_project_name("my-project") is True

    def test_valid_with_underscore(self):
        assert is_valid_project_name("my_project") is True

    def test_valid_with_numbers(self):
        assert is_valid_project_name("project123") is True

    def test_valid_mixed(self):
        assert is_valid_project_name("my-project_123") is True

    def test_invalid_empty(self):
        assert is_valid_project_name("") is False

    def test_invalid_with_space(self):
        assert is_valid_project_name("my project") is False

    def test_invalid_with_slash(self):
        assert is_valid_project_name("project/name") is False

    def test_invalid_cyrillic(self):
        assert is_valid_project_name("проект") is False

    def test_invalid_special_chars(self):
        assert is_valid_project_name("project@name") is False
