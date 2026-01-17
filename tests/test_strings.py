"""Tests for strings module."""
from codogram import strings


def test_url_validation_strings_exist():
    assert hasattr(strings, 'GIT_URL_INVALID_WIKI')
    assert hasattr(strings, 'GIT_URL_INVALID_BLOB')
    assert hasattr(strings, 'GIT_URL_INVALID_GIST')
    assert hasattr(strings, 'GIT_URL_INVALID_FORMAT')
    assert hasattr(strings, 'GIT_URL_RETRY_PROMPT')
    assert "[x]" in strings.GIT_URL_INVALID_WIKI  # Uses STATUS_ERR
