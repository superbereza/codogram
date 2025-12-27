import pytest
from codogram.screen import parse_screen, PermissionPrompt, ToolProgress, Idle

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

def test_parse_idle():
    idle_screen = "> some prompt\n──────────────"
    result = parse_screen(idle_screen)
    assert isinstance(result, Idle)

