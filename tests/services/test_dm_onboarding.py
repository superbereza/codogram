"""Tests for DM onboarding service."""
import pytest
from unittest.mock import patch


def test_get_slide_content_returns_slides():
    """Should return slide content for valid index."""
    from codogram.services.dm_onboarding import get_slide_content

    slide0 = get_slide_content(0)
    slide1 = get_slide_content(1)
    slide2 = get_slide_content(2)

    assert "Мобильность" in slide0
    assert "Асинхронность" in slide1
    assert "Команда" in slide2


def test_get_slide_content_returns_none_for_invalid():
    """Should return None for invalid slide index."""
    from codogram.services.dm_onboarding import get_slide_content

    assert get_slide_content(-1) is None
    assert get_slide_content(99) is None


def test_get_total_slides():
    """Should return correct number of slides."""
    from codogram.services.dm_onboarding import get_total_slides

    assert get_total_slides() == 3


def test_format_validation_errors():
    """Should format validation errors with fix hints."""
    from codogram.services.dm_onboarding import format_validation_errors
    from codogram.services.dm_onboarding.validation import ValidationResult

    results = [
        ValidationResult(ok=False, name="test1", message="Error 1", fix_hint="Fix 1"),
        ValidationResult(ok=False, name="test2", message="Error 2", fix_hint=""),
    ]

    formatted = format_validation_errors(results)

    assert "Error 1" in formatted
    assert "Fix 1" in formatted
    assert "Error 2" in formatted
