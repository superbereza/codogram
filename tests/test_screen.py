import pytest
from codogram.screen import parse_screen, PermissionPrompt, ToolProgress, Idle, PromptType, _extract_options, StatusBar, parse_status_bar

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


# MCP Trust Prompt Tests

MCP_TRUST_SCREEN = """
╭──────────────────────────────────────────────────────────────────────╮
│ New MCP server found in .mcp.json: telegram                         │
│                                                                      │
│ ❯ 1. Use this and all future MCP servers in this project            │
│   2. Use this MCP server                                            │
│   3. Continue without using this MCP server                         │
╰──────────────────────────────────────────────────────────────────────╯
   Enter to confirm · Esc to reject
"""

def test_parse_mcp_trust_prompt_basic():
    """MCP trust prompt should be detected."""
    from codogram.screen import _parse_mcp_trust_prompt
    lines = MCP_TRUST_SCREEN.split("\n")
    result = _parse_mcp_trust_prompt(lines)
    assert result is not None
    assert isinstance(result, PermissionPrompt)
    assert len(result.options) == 3
    assert "Use this and all future" in result.options[0]

def test_parse_mcp_trust_prompt_type():
    """MCP prompt should have MCP_TRUST type."""
    from codogram.screen import _parse_mcp_trust_prompt
    lines = MCP_TRUST_SCREEN.split("\n")
    result = _parse_mcp_trust_prompt(lines)
    assert result.prompt_type == PromptType.MCP_TRUST

def test_parse_mcp_trust_prompt_body():
    """MCP prompt body should contain server name."""
    from codogram.screen import _parse_mcp_trust_prompt
    lines = MCP_TRUST_SCREEN.split("\n")
    result = _parse_mcp_trust_prompt(lines)
    assert "telegram" in result.body or "MCP server" in result.body

def test_parse_mcp_trust_prompt_incomplete():
    """Incomplete box (no bottom corner) should return None."""
    from codogram.screen import _parse_mcp_trust_prompt
    incomplete = """
╭─────────────────────────╮
│ Some content            │
│ ❯ 1. Option             │
"""
    result = _parse_mcp_trust_prompt(incomplete.split("\n"))
    assert result is None

def test_parse_mcp_trust_prompt_no_options():
    """Box without numbered options should return None."""
    from codogram.screen import _parse_mcp_trust_prompt
    no_options = """
╭─────────────────────────╮
│ Just a box              │
│ No options here         │
╰─────────────────────────╯
"""
    result = _parse_mcp_trust_prompt(no_options.split("\n"))
    assert result is None

def test_parse_mcp_trust_prompt_last_box():
    """Multiple boxes on screen - should parse the LAST complete box."""
    from codogram.screen import _parse_mcp_trust_prompt
    multiple_boxes = """
Some scrollback text

╭─────────────────────────╮
│ Old box from scrollback │
│ ❯ 1. Old option         │
╰─────────────────────────╯

More text between boxes

╭─────────────────────────────────────────────────────╮
│ New MCP server found in .mcp.json: telegram         │
│ ❯ 1. Use this and all future MCP servers            │
│   2. Use this MCP server                            │
╰─────────────────────────────────────────────────────╯
   Enter to confirm
"""
    result = _parse_mcp_trust_prompt(multiple_boxes.split("\n"))
    assert result is not None
    assert "Use this and all future" in result.options[0]
    assert "telegram" in result.body

def test_parse_mcp_trust_prompt_false_positive():
    """Box with arrow but not in numbered format should return None."""
    from codogram.screen import _parse_mcp_trust_prompt
    false_positive = """
╭─────────────────────────╮
│ Some code output:       │
│ ❯ Not a real option     │
│ just arrow symbol       │
╰─────────────────────────╯
"""
    result = _parse_mcp_trust_prompt(false_positive.split("\n"))
    assert result is None


# Integration tests: parse_screen() with MCP prompts

def test_parse_screen_detects_mcp_prompt():
    """parse_screen should detect MCP trust prompt."""
    result = parse_screen(MCP_TRUST_SCREEN)
    assert isinstance(result, PermissionPrompt)
    assert result.prompt_type == PromptType.MCP_TRUST
    assert len(result.options) == 3

def test_parse_screen_regular_still_works():
    """Regular prompts should still work and have REGULAR type."""
    result = parse_screen(PERMISSION_SCREEN)
    assert isinstance(result, PermissionPrompt)
    assert result.prompt_type == PromptType.REGULAR

def test_parse_screen_mcp_priority():
    """MCP prompt should be detected even if regular patterns also present."""
    mixed_screen = """
Some tool output
──────────────────────────────────────────────────────
Some text after separator

╭─────────────────────────────────────────────────────╮
│ New MCP server found in .mcp.json: telegram         │
│ ❯ 1. Use this and all future MCP servers            │
│   2. Use this MCP server                            │
╰─────────────────────────────────────────────────────╯
   Enter to confirm
"""
    result = parse_screen(mixed_screen)
    assert isinstance(result, PermissionPrompt)
    assert result.prompt_type == PromptType.MCP_TRUST


# StatusBar Tests

class TestParseStatusBar:
    def test_parse_accept_edits_mode(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏵⏵ accept edits on (shift+tab to               Context left until
  cycle)                                         auto-compact: 45%
"""
        result = parse_status_bar(output)
        assert result.approval_mode == "accept edits"
        assert result.context_percent == 45

    def test_parse_plan_mode(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏸ plan mode on (shift+tab to cycle)
"""
        result = parse_status_bar(output)
        assert result.approval_mode == "plan mode"

    def test_parse_default_mode(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ? for shortcuts
"""
        result = parse_status_bar(output)
        assert result.approval_mode is None  # default mode

    def test_parse_background_tasks(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏵⏵ accept edits on · 2 background tasks
"""
        result = parse_status_bar(output)
        assert result.background_tasks == 2

    def test_parse_no_background_tasks(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏵⏵ accept edits on (shift+tab to cycle)
"""
        result = parse_status_bar(output)
        assert result.background_tasks == 0

    def test_parse_context_not_displayed(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  1 background task
"""
        result = parse_status_bar(output)
        assert result.context_percent is None

    def test_parse_empty_output(self):
        """Empty output returns default values."""
        result = parse_status_bar("")
        assert result.approval_mode is None  # default mode
        assert result.background_tasks == 0
        assert result.context_percent is None

    def test_parse_only_background_tasks(self):
        """When only background tasks visible (during generation)."""
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  2 background tasks
"""
        result = parse_status_bar(output)
        assert result.approval_mode is None  # default mode
        assert result.background_tasks == 2
        assert result.context_percent is None


# Thinking Status Tests

from codogram.screen import parse_thinking_status


def test_parse_thinking_status_basic():
    """Parse basic thinking status line."""
    output = """
Some previous output
· Wibbling… (ctrl+c to interrupt)
────────────────────────────────────────
❯
────────────────────────────────────────
"""
    result = parse_thinking_status(output)
    assert result == "· Wibbling… (/esc to interrupt)"


def test_parse_thinking_status_with_details():
    """Parse thinking status with time and tokens."""
    output = """
✶ Hatching… (ctrl+c to interrupt · 30s · ↓ 914 tokens · thinking)
────────────────────────────────────────
"""
    result = parse_thinking_status(output)
    assert result == "✶ Hatching… (/esc to interrupt · 30s · ↓ 914 tokens · thinking)"


def test_parse_thinking_status_esc():
    """Parse with esc instead of ctrl+c."""
    output = "· Thinking… (esc to interrupt · 5s)"
    result = parse_thinking_status(output)
    assert result == "· Thinking… (/esc to interrupt · 5s)"


def test_parse_thinking_status_cooked():
    """Parse completion status."""
    output = "✻ Cooked for 35s\n────────"
    result = parse_thinking_status(output)
    assert result == "✻ Cooked for 35s"


def test_parse_thinking_status_none():
    """Return None when no thinking status."""
    output = """
────────────────────────────────────────
❯
────────────────────────────────────────
"""
    result = parse_thinking_status(output)
    assert result is None
