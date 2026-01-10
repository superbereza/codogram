import pytest
from codogram.screen import parse_screen, PermissionPrompt, ToolProgress, Idle, PromptType, _extract_options

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

def test_regular_prompt_has_regular_type():
    """Existing permission prompts should have REGULAR type."""
    result = parse_screen(PERMISSION_SCREEN)
    assert isinstance(result, PermissionPrompt)
    assert result.prompt_type == PromptType.REGULAR


def test_extract_options_basic():
    """Extract options from lines with selector."""
    lines = [
        "Some body text",
        "More body",
        " ❯ 1. Yes",
        "   2. No",
        " Esc to cancel",
    ]
    body_lines, options = _extract_options(lines)
    assert options == ["1. Yes", "2. No"]
    assert "Some body text" in body_lines[0]


def test_extract_options_empty():
    """No selector means no options."""
    lines = ["Just text", "No selector here"]
    body_lines, options = _extract_options(lines)
    assert options == []
    assert len(body_lines) == 2


def test_extract_options_reusable():
    """_extract_options works in different contexts (MCP, regular, no-separator)."""
    # MCP-style content (stripped from box)
    mcp_lines = [
        "New MCP server found in .mcp.json: telegram",
        "",
        "❯ 1. Use this and all future MCP servers",
        "  2. Use this MCP server",
        "  3. Continue without",
    ]
    body, opts = _extract_options(mcp_lines)
    assert len(opts) == 3
    assert "MCP server" in body[0]

    # Regular permission style
    regular_lines = [
        "Do you want to create test.txt?",
        " ❯ 1. Yes",
        "   2. Yes, allow all",
        " Esc to cancel",
    ]
    body2, opts2 = _extract_options(regular_lines)
    assert opts2 == ["1. Yes", "2. Yes, allow all"]


def test_parse_screen_after_refactor():
    """Existing behavior unchanged after _extract_options refactoring."""
    # Regular permission prompt
    result = parse_screen(PERMISSION_SCREEN)
    assert isinstance(result, PermissionPrompt)
    assert len(result.options) >= 2
    assert "Yes" in result.options[0]
    # Body should contain file info
    assert "test.txt" in result.body

