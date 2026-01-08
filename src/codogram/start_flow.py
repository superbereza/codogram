"""Conversation flow for /start command."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def dir_not_found_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for when directory not found."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Create", callback_data="start:create_dir"),
            InlineKeyboardButton(text="Different path", callback_data="start:custom_path"),
        ]
    ])


def git_setup_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for git setup options - column layout."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="git init", callback_data="start:git_init")],
        [InlineKeyboardButton(text="git init + gh repo create", callback_data="start:git_gh")],
        [InlineKeyboardButton(text="git clone", callback_data="start:git_clone")],
        [InlineKeyboardButton(text="No git", callback_data="start:no_git")],
    ])


def git_visibility_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for GitHub repo visibility."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Private", callback_data="start:gh_private"),
            InlineKeyboardButton(text="Public", callback_data="start:gh_public"),
        ]
    ])


def restart_confirm_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for restart confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes, restart", callback_data="restart:confirm"),
            InlineKeyboardButton(text="Cancel", callback_data="restart:cancel"),
        ]
    ])


def launch_confirm_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for launch confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Launch", callback_data="start:launch_claude"),
            InlineKeyboardButton(text="Cancel", callback_data="start:cancel"),
        ]
    ])
