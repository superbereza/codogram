# tests/test_menu_service.py
import pytest
from codogram.services.menu import BASIC_COMMANDS, FORUM_COMMANDS, register_menu_for_chat


def test_basic_commands_count():
    """Basic menu has 9 commands (no /branch, /finish)."""
    assert len(BASIC_COMMANDS) == 9


def test_forum_commands_count():
    """Forum menu has 11 commands (includes /branch, /finish)."""
    assert len(FORUM_COMMANDS) == 11


def test_basic_commands_order():
    """Basic commands follow the defined order."""
    commands = [c.command for c in BASIC_COMMANDS]
    assert commands == [
        "esc", "auto_accept", "thread", "clear",
        "start", "settings", "restart", "get_debug_ids", "help"
    ]


def test_forum_commands_order():
    """Forum commands follow the defined order with branch/finish."""
    commands = [c.command for c in FORUM_COMMANDS]
    assert commands == [
        "esc", "auto_accept", "thread", "branch", "clear", "finish",
        "start", "settings", "restart", "get_debug_ids", "help"
    ]


def test_basic_excludes_branch_finish():
    """Basic menu does not include /branch and /finish."""
    commands = [c.command for c in BASIC_COMMANDS]
    assert "branch" not in commands
    assert "finish" not in commands


def test_forum_includes_branch_finish():
    """Forum menu includes /branch and /finish."""
    commands = [c.command for c in FORUM_COMMANDS]
    assert "branch" in commands
    assert "finish" in commands


def test_register_menu_for_chat_callable():
    """register_menu_for_chat should be async callable."""
    import asyncio
    assert asyncio.iscoroutinefunction(register_menu_for_chat)
