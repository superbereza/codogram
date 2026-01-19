"""Tests for DM onboarding service."""
import pytest
from unittest.mock import patch


def test_get_slide_content_returns_slides():
    """Should return slide content for valid index."""
    from codogram.services.dm_onboarding import get_slide_content

    slide0 = get_slide_content(0)
    slide1 = get_slide_content(1)
    slide2 = get_slide_content(2)

    assert "Mobile" in slide0
    assert "Async" in slide1
    assert "Team" in slide2


def test_get_slide_content_returns_none_for_invalid():
    """Should return None for invalid slide index."""
    from codogram.services.dm_onboarding import get_slide_content

    assert get_slide_content(-1) is None
    assert get_slide_content(99) is None


def test_get_total_slides():
    """Should return correct number of slides."""
    from codogram.services.dm_onboarding import get_total_slides

    assert get_total_slides() == 3


def test_format_validation_checks():
    """Should format validation checks with status indicators."""
    from codogram.services.dm_onboarding import format_validation_checks
    from codogram.services.dm_onboarding.validation import ValidationResult

    results = [
        ValidationResult(ok=True, name="check1 ok", message=""),
        ValidationResult(ok=False, name="check2", message="Error 2", fix_hint="Fix 2"),
        ValidationResult(ok=False, name="check3", message="Error 3", fix_hint=""),
    ]

    formatted = format_validation_checks(results)

    assert "[v]" in formatted
    assert "check1 ok" in formatted
    assert "[x]" in formatted
    assert "Error 2" in formatted
    assert "Fix 2" in formatted
    assert "Error 3" in formatted
