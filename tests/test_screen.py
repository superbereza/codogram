import pytest
from telegram_bridge.screen import parse_screen, PermissionPrompt, ToolProgress, Idle

PERMISSION_SCREEN = """
● Write(test.txt)

──────────────────────────────────────────────────────────
 Create file test.txt
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 hello world
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to create test.txt?
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. Type here to tell Claude what to do differently

 Esc to cancel
"""

def test_parse_permission_prompt():
    result = parse_screen(PERMISSION_SCREEN)
    assert isinstance(result, PermissionPrompt)
    assert len(result.options) >= 2
    assert "Yes" in result.options[0]

PERMISSION_WITH_CONTENT = """
● Write(test.txt)

──────────────────────────────────────────────────────────
 Create file test.txt
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 hello world
  2 line two
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to create test.txt?
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. Type here to tell Claude what to do differently

 Esc to cancel
"""

def test_parse_permission_content():
    result = parse_screen(PERMISSION_WITH_CONTENT)
    assert isinstance(result, PermissionPrompt)
    assert result.description == "Create file test.txt"
    assert "hello world" in result.content
    assert "line two" in result.content
    assert result.question == "Do you want to create test.txt?"
    assert len(result.options) >= 2

def test_parse_idle():
    idle_screen = "> some prompt\n──────────────"
    result = parse_screen(idle_screen)
    assert isinstance(result, Idle)
