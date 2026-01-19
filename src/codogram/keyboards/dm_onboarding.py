"""Keyboards for DM onboarding and dashboard."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .. import strings


def carousel_keyboard(current_slide: int, total_slides: int) -> InlineKeyboardMarkup:
    """Build carousel navigation keyboard.

    Args:
        current_slide: 0-indexed current slide number
        total_slides: Total number of slides

    Returns:
        Keyboard with Prev/Next buttons based on position, plus "How to use" at bottom
    """
    nav_buttons = []

    if current_slide > 0:
        nav_buttons.append(InlineKeyboardButton(
            text=strings.BTN_PREV,
            callback_data=f"onb:slide:{current_slide - 1}"
        ))

    if current_slide < total_slides - 1:
        nav_buttons.append(InlineKeyboardButton(
            text=strings.BTN_NEXT,
            callback_data=f"onb:slide:{current_slide + 1}"
        ))

    # "How to use" button on second row - leads to validation
    how_to_use = InlineKeyboardButton(
        text=strings.BTN_HOW_TO_USE,
        callback_data=f"onb:slide:{total_slides}"  # triggers validation
    )

    rows = []
    if nav_buttons:
        rows.append(nav_buttons)
    rows.append([how_to_use])

    return InlineKeyboardMarkup(inline_keyboard=rows)


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
