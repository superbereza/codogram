"""Menu registration service for scope-based bot commands.

Single source of truth for command definitions.
BASIC_COMMANDS and FORUM_COMMANDS are derived from _ALL_COMMANDS.
"""
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeAllPrivateChats

# Single source: (command, description, is_basic)
# is_basic=True -> included in basic menu
# All commands included in forum menu
_ALL_COMMANDS = [
    ("esc", "Send Esc, stop current operation", True),
    ("shift_tab", "Cycle Claude approval mode", True),
    ("auto_accept", "Accept every Claude permission 🚧", True),
    ("new_chat", "Create new chat: topic & Claude session", True),
    ("finish_chat", "Archive chat and stop Claude", False),  # forum only
    ("start", "Connect or resume", True),
    ("settings", "Show settings", True),
    ("clear_context", "Clear current Claude context", True),
    ("reset_chat", "Restart Claude process", True),
    ("get_debug_ids", "Debug info", True),
    ("help", "Show help", True),
    ("hard_reset", "Full project reset", True),
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

# Setup commands (during onboarding)
SETUP_COMMANDS = [
    BotCommand(command="start", description="Restart setup"),
    BotCommand(command="reset_all", description="Cancel setup"),
    BotCommand(command="help", description="Get help"),
    BotCommand(command="get_debug_ids", description="Show debug IDs"),
]

# Private chat (DM) commands
DM_COMMANDS = [
    BotCommand(command="start", description="Start or show status"),
    BotCommand(command="settings", description="Global defaults"),
    BotCommand(command="dashboard", description="View all projects"),
    BotCommand(command="whisper_stats", description="Whisper API usage stats"),
    BotCommand(command="check_env", description="Check environment"),
    BotCommand(command="intro", description="Show intro again"),
]


async def register_dm_commands(bot: Bot) -> None:
    """Register commands for all private chats."""
    scope = BotCommandScopeAllPrivateChats()
    await bot.set_my_commands(DM_COMMANDS, scope=scope)


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
