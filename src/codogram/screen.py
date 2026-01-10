import re
from dataclasses import dataclass
from enum import Enum


class PromptType(Enum):
    REGULAR = "regular"
    MCP_TRUST = "mcp_trust"


@dataclass
class PermissionPrompt:
    options: list[str]  # ["1. Yes", "2. Yes, allow all..."]
    body: str = ""      # Everything between ──── and ❯ (description + content + question)
    prompt_type: PromptType = PromptType.REGULAR

@dataclass
class ToolProgress:
    tool: str
    output: str

@dataclass
class Idle:
    pass

ScreenState = PermissionPrompt | ToolProgress | Idle

# Separators for display
SEPARATOR_DASHED = " " + "- " * 18


def _extract_options(lines: list[str]) -> tuple[list[str], list[str]]:
    """Extract options from lines containing selector.

    Returns:
        (body_lines, options) tuple
    """
    options = []
    body_lines = []
    in_options = False

    for line in lines:
        if "❯" in line:
            in_options = True
            # NOTE: Keep exact regex from existing code
            match = re.match(r'\s*❯\s*(\d+\.\s+.+)', line)
            if match:
                options.append(match.group(1).strip())
        elif in_options:
            # NOTE: \s{2,} (2+ spaces) - NOT \s* - to avoid false positives
            match = re.match(r'\s{2,}(\d+\.\s+.+)', line)
            if match:
                options.append(match.group(1).strip())
            elif line.strip().startswith(("Esc", "Enter")):
                break
        else:
            body_lines.append(line)

    return body_lines, options


def parse_screen(output: str) -> ScreenState:
    """Parse tmux capture-pane output to detect state."""

    lines = output.split("\n")

    # Find last solid separator ────
    last_sep_idx = -1
    for i, line in enumerate(lines):
        if "─" * 10 in line:
            last_sep_idx = i

    if last_sep_idx == -1:
        # No separator - but check if there's ❯ with numbered options (trust folder prompt, etc.)
        if "❯" in output:
            result = _parse_options_without_separator(lines)
            if result:
                return result
        return _check_tool_progress(output)

    # Get lines after separator
    after_sep = lines[last_sep_idx + 1:]

    # Check: if there's ● after separator, it's not a permission prompt
    for line in after_sep:
        # Tool markers: "● ToolName(" — bullet, word, open paren
        # Submit review: "● Question text?" — no paren after first word
        if re.match(r'^\s*●\s+\w+\(', line):
            return _check_tool_progress(output)

    # Use shared option extraction
    body_lines, options = _extract_options(after_sep)

    if not options:
        return _check_tool_progress(output)

    # Format body: replace ╌╌╌ with pretty separator
    body = "\n".join(body_lines)
    body = re.sub(r'╌{10,}', SEPARATOR_DASHED, body)
    body = body.strip()

    return PermissionPrompt(options=options, body=body)


def _parse_options_without_separator(lines: list[str]) -> PermissionPrompt | None:
    """Parse permission prompt without solid separator (e.g., trust folder prompt).

    Looks for ❯ with numbered options even without ──── separator.
    """
    body_lines, options = _extract_options(lines)

    if not options:
        return None

    body = "\n".join(body_lines).strip()
    return PermissionPrompt(options=options, body=body)


def _check_tool_progress(output: str) -> ScreenState:
    """Check for tool progress indicators."""
    progress_match = re.search(r'[●✶]\s*(\w+)\(([^)]*)\)', output)
    if progress_match and "❯" not in output:
        tool = progress_match.group(1)
        lines = output.strip().split("\n")
        output_lines = []
        for line in lines:
            if line.strip().startswith("⎿") or (line.strip() and not line.strip().startswith(("●", "✶", ">", "─"))):
                output_lines.append(line.strip())
        return ToolProgress(tool=tool, output="\n".join(output_lines[-5:]))
    return Idle()


def is_claude_ready(output: str) -> bool:
    """Check if Claude UI is loaded and ready for input.

    Multiple detection strategies (any match = ready):
    1. Input area: two solid lines (────) — most stable
    2. "> Try" prompt suggestion
    3. "? for shortcuts" indicator
    """
    if not output:
        return False

    # Strategy 1: Input area - two horizontal lines (most stable)
    # The input box has ──────── above and below
    lines = output.split('\n')
    solid_line_count = 0
    for line in lines:
        if '─' * 10 in line:
            solid_line_count += 1
            if solid_line_count >= 2:
                return True

    # Strategy 2: "> Try" prompt
    if "> Try" in output:
        return True

    # Strategy 3: "? for shortcuts"
    if "? for shortcuts" in output:
        return True

    return False
