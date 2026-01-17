import pytest
from codogram.utils.truncate import truncate_body

MAX_LINES = 5


def test_truncate_body_short_text():
    """Text under limit is returned as-is."""
    text = "line1\nline2\nline3"
    result = truncate_body(text, verbose=False)
    assert result == text
    assert "[truncated]" not in result


def test_truncate_body_exact_limit():
    """Text at exactly 5 lines is returned as-is."""
    text = "\n".join([f"line{i}" for i in range(5)])
    result = truncate_body(text, verbose=False)
    assert result == text
    assert "[truncated]" not in result


def test_truncate_body_over_limit():
    """Text over 5 lines is truncated with indicator."""
    text = "\n".join([f"line{i}" for i in range(10)])
    result = truncate_body(text, verbose=False)
    lines = result.split("\n")
    assert len(lines) == 6  # 5 lines + "[truncated]"
    assert lines[-1] == "[truncated]"


def test_truncate_body_verbose_mode():
    """In verbose mode, text is returned as-is regardless of length."""
    text = "\n".join([f"line{i}" for i in range(20)])
    result = truncate_body(text, verbose=True)
    assert result == text
    assert "[truncated]" not in result


def test_truncate_body_none():
    """None input returns None."""
    assert truncate_body(None, verbose=False) is None


def test_truncate_body_empty():
    """Empty string returns empty string."""
    assert truncate_body("", verbose=False) == ""
