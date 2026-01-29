"""Keyboards for avatar pack prompts."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ... import strings


def avatar_pack_create_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for 'Create avatar pack?' prompt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=strings.EMOJI_PACK_BTN_CREATE,
                callback_data="avatar_pack:create"
            ),
            InlineKeyboardButton(
                text=strings.EMOJI_PACK_BTN_NOT_NOW,
                callback_data="avatar_pack:cancel"
            ),
        ]
    ])


def avatar_pack_disable_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for 'Disable avatar pack?' prompt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=strings.EMOJI_PACK_BTN_DISABLE,
                callback_data="avatar_pack:disable"
            ),
            InlineKeyboardButton(
                text=strings.EMOJI_PACK_BTN_KEEP,
                callback_data="avatar_pack:cancel"
            ),
        ]
    ])
