"""Tests for DM onboarding keyboards."""
import pytest


def test_carousel_keyboard_first_slide():
    """First slide should only have Next button."""
    from codogram.keyboards.dm_onboarding import carousel_keyboard

    kb = carousel_keyboard(current_slide=0, total_slides=3)
    buttons = kb.inline_keyboard[0]

    assert len(buttons) == 1
    assert buttons[0].text == "Далее →"
    assert buttons[0].callback_data == "onb:slide:1"


def test_carousel_keyboard_middle_slide():
    """Middle slides should have both Prev and Next buttons."""
    from codogram.keyboards.dm_onboarding import carousel_keyboard

    kb = carousel_keyboard(current_slide=1, total_slides=3)
    buttons = kb.inline_keyboard[0]

    assert len(buttons) == 2
    assert buttons[0].text == "← Назад"
    assert buttons[0].callback_data == "onb:slide:0"
    assert buttons[1].text == "Далее →"
    assert buttons[1].callback_data == "onb:slide:2"


def test_carousel_keyboard_last_slide():
    """Last slide should only have Prev button."""
    from codogram.keyboards.dm_onboarding import carousel_keyboard

    kb = carousel_keyboard(current_slide=2, total_slides=3)
    buttons = kb.inline_keyboard[0]

    assert len(buttons) == 1
    assert buttons[0].text == "← Назад"
    assert buttons[0].callback_data == "onb:slide:1"


def test_validation_recheck_keyboard():
    """Should have recheck button."""
    from codogram.keyboards.dm_onboarding import validation_recheck_keyboard

    kb = validation_recheck_keyboard()
    buttons = kb.inline_keyboard[0]

    assert len(buttons) == 1
    assert buttons[0].callback_data == "onb:recheck"


def test_dashboard_keyboard():
    """Should have refresh button."""
    from codogram.keyboards.dm_onboarding import dashboard_keyboard

    kb = dashboard_keyboard()
    buttons = kb.inline_keyboard[0]

    assert len(buttons) == 1
    assert buttons[0].callback_data == "dash:refresh"
