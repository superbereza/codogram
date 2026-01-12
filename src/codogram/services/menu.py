"""Menu registration service for scope-based bot commands.

Single source of truth for command definitions.
BASIC_COMMANDS and FORUM_COMMANDS are derived from _ALL_COMMANDS.
"""
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat

# Single source: (command, description, is_basic)
# is_basic=True -> included in basic menu
# All commands included in forum menu
_ALL_COMMANDS = [
    ("esc", "Cancel current operation", True),
    ("auto_accept", "Toggle auto-accept mode", True),
    ("thread", "New topic in project directory", True),
    ("branch", "New isolated feature branch + topic", False),  # forum only
    ("clear", "Clear context, start fresh", True),
    ("finish", "Merge branch, archive topic", False),  # forum only
    ("start", "Connect Claude or show status", True),
    ("settings", "View current settings", True),
    ("shift_tab", "Cycle Claude approval mode", True),
    ("restart", "Force restart Claude", True),
    ("get_debug_ids", "Show chat and thread IDs", True),
    ("help", "List all commands", True),
]

# Derived lists (no duplication)
BASIC_COMMANDS = [
    BotCommand(command=cmd, description=desc)
    for cmd, desc, is_basic in _ALL_COMMANDS if is_basic
]

FORUM_COMMANDS = [
    BotCommand(command=cmd, description=desc)
    for cmd, desc, _ in _ALL_COMMANDS
]


async def register_menu_for_chat(bot: Bot, chat_id: int, is_forum: bool) -> None:
    """Register scope-based menu for a specific chat.

    Args:
        bot: Telegram bot instance
        chat_id: Target chat ID
        is_forum: True for forum (supergroup with topics), False for regular group
    """
    commands = FORUM_COMMANDS if is_forum else BASIC_COMMANDS
    scope = BotCommandScopeChat(chat_id=chat_id)
    await bot.set_my_commands(commands, scope=scope)
