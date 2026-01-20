# src/codogram/keyboards/setup/git_choice.py
"""Git setup choice keyboard."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ... import strings


def git_choice_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for git setup options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_GIT_INIT, callback_data="git:init")],
        [InlineKeyboardButton(text=strings.BTN_GIT_GH, callback_data="git:gh")],
        [InlineKeyboardButton(text=strings.BTN_GIT_CLONE, callback_data="git:clone")],
        [InlineKeyboardButton(text=strings.BTN_GIT_NONE, callback_data="git:none")],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="git:back")],
    ])


def visibility_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for repository visibility choice."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_VISIBILITY_PRIVATE, callback_data="visibility:private"),
            InlineKeyboardButton(text=strings.BTN_VISIBILITY_PUBLIC, callback_data="visibility:public"),
        ],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="visibility:back")],
    ])
