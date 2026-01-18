"""Keyboards for DM onboarding and dashboard."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .. import strings


def carousel_keyboard(current_slide: int, total_slides: int) -> InlineKeyboardMarkup:
    """Build carousel navigation keyboard.

    Args:
        current_slide: 0-indexed current slide number
        total_slides: Total number of slides

    Returns:
        Keyboard with Prev/Next buttons based on position
    """
    buttons = []

    if current_slide > 0:
        buttons.append(InlineKeyboardButton(
            text=strings.BTN_PREV,
            callback_data=f"onb:slide:{current_slide - 1}"
        ))

    if current_slide < total_slides - 1:
        buttons.append(InlineKeyboardButton(
            text=strings.BTN_NEXT,
            callback_data=f"onb:slide:{current_slide + 1}"
        ))

    return InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])


def validation_recheck_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard with recheck button for failed validation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=strings.BTN_RECHECK,
            callback_data="onb:recheck"
        )]
    ])


def dashboard_keyboard() -> InlineKeyboardMarkup:
    """Build dashboard keyboard with refresh button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=strings.BTN_REFRESH,
            callback_data="dash:refresh"
        )]
    ])
