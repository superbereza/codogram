"""Conversation flow for /start command."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def dir_not_found_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for when directory not found."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Создать", callback_data="start:create_dir"),
            InlineKeyboardButton(text="Указать другую", callback_data="start:custom_path"),
        ]
    ])


def git_setup_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for git setup options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="init локально", callback_data="start:git_init"),
            InlineKeyboardButton(text="init + gh create", callback_data="start:git_gh"),
        ],
        [
            InlineKeyboardButton(text="git clone", callback_data="start:git_clone"),
            InlineKeyboardButton(text="нет", callback_data="start:no_git"),
        ],
    ])


def git_visibility_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for GitHub repo visibility."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Private", callback_data="start:gh_private"),
            InlineKeyboardButton(text="Public", callback_data="start:gh_public"),
        ]
    ])
