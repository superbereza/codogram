"""Tests for domain validators."""
import pytest

from codogram.domain.validators import (
    is_valid_project_name,
    sanitize_project_name,
    MAX_PROJECT_NAME_LENGTH,
)


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


class TestMaxProjectNameLength:
    def test_constant_is_35(self):
        assert MAX_PROJECT_NAME_LENGTH == 35

    def test_valid_name_at_max_length(self):
        name = "a" * 35
        assert is_valid_project_name(name) is True

    def test_invalid_name_over_max_length(self):
        name = "a" * 36
        assert is_valid_project_name(name) is False


class TestSanitizeProjectName:
    def test_simple_title(self):
        assert sanitize_project_name("MyProject") == "MyProject"

    def test_title_with_spaces(self):
        assert sanitize_project_name("My Project") == "My-Project"

    def test_title_with_special_chars(self):
        assert sanitize_project_name("My Project!@#") == "My-Project"

    def test_title_with_multiple_spaces(self):
        assert sanitize_project_name("My   Project") == "My-Project"

    def test_cyrillic_title(self):
        # Cyrillic gets replaced with dashes, then stripped
        result = sanitize_project_name("Мой проект")
        assert result is None or result == ""

    def test_empty_after_sanitize(self):
        assert sanitize_project_name("!!!") is None

    def test_too_long_gets_none(self):
        long_title = "a" * 50
        assert sanitize_project_name(long_title) is None

    def test_preserves_valid_chars(self):
        assert sanitize_project_name("my-project_123") == "my-project_123"
