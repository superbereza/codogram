# src/codogram/claude/tool_formatter.py
"""Format tool calls for Telegram display."""

from pathlib import Path

from .. import strings
from ..utils.truncate import truncate_body


def _get_brief_context(tool_name: str, tool_input: dict | None) -> str | None:
    """Get brief context for headers/current mode.

    Returns short description like:
    - Bash: "Restart bot" (from description) or first 40 chars of command
    - Read/Write/Edit: ".../filename.py"
    - Glob/Grep: pattern
    - Task: description
    """
    if not tool_input:
        return None

    if tool_name == "Bash":
        # Prefer description, fallback to command snippet
        desc = tool_input.get("description")
        if desc:
            return desc[:50]
        cmd = tool_input.get("command", "")
        # First line, truncated
        first_line = cmd.split("\n")[0][:40]
        return f"`{first_line}`" if first_line else None

    elif tool_name in ("Read", "Write", "Edit"):
        path = tool_input.get("file_path", "")
        if path:
            # Show .../parent/filename.py
            p = Path(path)
            if len(p.parts) > 2:
                return f"`.../{ p.parts[-2]}/{p.name}`"
            return f"`{p.name}`"

    elif tool_name in ("Glob", "Grep"):
        pattern = tool_input.get("pattern", "")
        if pattern:
            return f"`{pattern[:40]}`"

    elif tool_name == "Task":
        desc = tool_input.get("description", "")
        if desc:
            return desc[:50]

    elif tool_name == "TaskCreate":
        subject = tool_input.get("subject", "")
        if subject:
            return subject[:50]

    elif tool_name == "TaskUpdate":
        status = tool_input.get("status", "")
        task_id = tool_input.get("taskId", "")
        if status:
            return f"#{task_id} → {status}"

    elif tool_name == "Skill":
        skill = tool_input.get("skill", "")
        if skill:
            return skill

    elif tool_name.startswith("mcp__"):
        # MCP tools: mcp__telegram__list_messages → telegram: list_messages
        parts = tool_name.split("__")
        if len(parts) >= 3:
            return f"{parts[1]}: {parts[2]}"

    return None


def format_tool_use(
    tool_name: str,
    tool_input: dict | None,
    display_mode: str = "lines",
    line_limit: int = 5,
    display_bullet: bool = True,
) -> str | None:
    """Format tool use for Telegram display.

    Args:
        tool_name: Name of the tool (Bash, Read, etc.)
        tool_input: Tool input dict
        display_mode: show_all, lines, headers, current, silence
        line_limit: Lines to show in 'lines' mode
        display_bullet: Show bullet prefix

    Returns:
        Formatted string or None if should be hidden (silence mode)
    """
    if display_mode == "silence":
        return None

    bullet = "● " if display_bullet else ""

    # Headers/current mode - tool name + brief context
    if display_mode in ("headers", "current"):
        brief = _get_brief_context(tool_name, tool_input)
        if brief:
            return f"{bullet}**{tool_name}**: {brief}"
        return f"{bullet}**{tool_name}**"

    if not tool_input:
        return f"{bullet}**{tool_name}**"

    # Determine verbosity for truncation
    verbose = display_mode == "show_all"

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        # Safety limits to prevent Telegram API errors
        char_limit = 3500 if verbose else 500
        was_truncated = len(cmd) > char_limit
        cmd = cmd[:char_limit]
        desc = tool_input.get("description", "")
        cmd_display = truncate_body(cmd, verbose=verbose, max_lines=line_limit) or cmd
        if was_truncated and strings.SNIP not in cmd_display:
            cmd_display += f"\n{strings.SNIP}"
        if desc:
            return f"{bullet}**Bash**: {desc}\n`{cmd_display}`"
        return f"{bullet}**Bash**\n`{cmd_display}`"

    elif tool_name == "Read":
        path = tool_input.get("file_path", "")
        return f"{bullet}**Read** `{path}`"

    elif tool_name == "Write":
        path = tool_input.get("file_path", "")
        return f"{bullet}**Write** `{path}`"

    elif tool_name == "Edit":
        path = tool_input.get("file_path", "")
        return f"{bullet}**Edit** `{path}`"

    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"{bullet}**Glob** `{pattern}`"

    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"{bullet}**Grep** `{pattern}`"

    elif tool_name == "Task":
        desc = tool_input.get("description", "")
        return f"{bullet}**Task**: {desc}"

    elif tool_name == "TodoWrite":
        return f"{bullet}**TodoWrite**"

    elif tool_name == "Skill":
        skill = tool_input.get("skill", "")
        return f"{bullet}**Skill**: {skill}"

    elif tool_name.startswith("mcp__"):
        # MCP tools: mcp__telegram__list_messages → telegram: list_messages
        parts = tool_name.split("__")
        if len(parts) >= 3:
            service = parts[1]
            method = parts[2]
            return f"{bullet}**{service}**: {method}"
        return f"{bullet}**{tool_name}**"

    else:
        preview_raw = str(tool_input)
        was_truncated = len(preview_raw) > 200
        preview = preview_raw[:200]
        preview = truncate_body(preview, verbose=verbose, max_lines=line_limit) or preview
        if was_truncated and strings.SNIP not in preview:
            preview += f"\n{strings.SNIP}"
        return f"{bullet}**{tool_name}**\n`{preview}`"
