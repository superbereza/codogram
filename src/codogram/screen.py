import re
from dataclasses import dataclass
from enum import Enum

# Claude thinking status spinners (unique Unicode chars)
# Excluded: * (too common in text) and · (middle dot, appears in bullet lists)
# These remaining chars are specific enough to not need content validation
THINKING_SPINNERS = "✶✻✽✢"


# Pattern for pasted content placeholder: [Pasted text #1 +51 lines]
PASTED_PATTERN = re.compile(r'\[Pasted text #\d+ \+\d+ lines?\]')


def extract_input_text(screen: str) -> str | None:
    """Extract text from Claude's input line (after ❯).

    Returns None if input is empty or not found.
    Used for stuck message detection.
    """
    for line in screen.split("\n"):
        stripped = line.strip()
        if stripped.startswith("❯"):
            # Text after ❯
            text = stripped[1:].strip()
            return text if text else None
    return None


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


@dataclass
class StatusBar:
    """Claude CLI status bar state."""
    approval_mode: str | None  # "accept edits", "plan mode", None (default)
    background_tasks: int      # 0, 1, 2...
    context_percent: int | None  # 0-100 or None if not displayed

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


def _parse_mcp_trust_prompt(lines: list[str]) -> PermissionPrompt | None:
    """Parse MCP server trust prompt (box-style UI).

    Format:
    ╭────────────────────────────────╮
    │ New MCP server found...        │
    │ ❯ 1. Use this and all future   │
    │   2. Use this MCP server       │
    ╰────────────────────────────────╯
       Enter to confirm · Esc to reject

    Returns PermissionPrompt with MCP_TRUST type, or None if not MCP prompt.
    """
    # Find ALL complete boxes, then use the LAST one
    boxes = []  # List of (start_idx, end_idx) tuples
    box_start = None
    for i, line in enumerate(lines):
        if "╭" in line:
            box_start = i
        elif "╰" in line and box_start is not None:
            boxes.append((box_start, i))
            box_start = None  # Reset for next box

    if not boxes:
        return None

    # Use the LAST complete box
    box_start, box_end = boxes[-1]

    # Extract content between │...│
    content_lines = []
    for line in lines[box_start + 1 : box_end]:
        if "│" in line:
            # Split by │ and take middle content
            parts = line.split("│")
            if len(parts) >= 3:
                # Keep original spacing for option detection
                content_lines.append(parts[1])
            elif len(parts) == 2:
                content_lines.append(parts[1])

    if not content_lines:
        return None

    body_lines, options = _extract_options(content_lines)

    if not options:
        return None

    # Strip body lines for clean output
    body = "\n".join(line.strip() for line in body_lines).strip()
    return PermissionPrompt(
        options=options,
        body=body,
        prompt_type=PromptType.MCP_TRUST
    )


def parse_screen(output: str) -> ScreenState:
    """Parse tmux capture-pane output to detect state.

    Parsing order (most specific first):
    1. MCP trust prompt (box-style) — ╭╮╯╰│ characters
    2. Regular permission prompt — ──── separator + ❯ options
    3. Permission without separator — ❯ options only (trust folder)
    4. Tool progress — ● or ✶ markers
    5. Idle — default
    """
    lines = output.split("\n")

    # 1. Try MCP trust prompt first (most specific)
    mcp_result = _parse_mcp_trust_prompt(lines)
    if mcp_result:
        return mcp_result

    # 2. Find all solid separators ────
    sep_indices = []
    for i, line in enumerate(lines):
        if "─" * 10 in line:
            sep_indices.append(i)

    if not sep_indices:
        # No separator - but check if there's ❯ with numbered options (trust folder prompt, etc.)
        if "❯" in output:
            result = _parse_options_without_separator(lines)
            if result:
                return result
        return _check_tool_progress(output)

    # AskUserQuestion has options BETWEEN two separators
    # Regular prompts have options AFTER the last separator
    if len(sep_indices) >= 2:
        # Try between last two separators first (AskUserQuestion format)
        start_idx = sep_indices[-2]
        end_idx = sep_indices[-1]
        between_sep = lines[start_idx + 1:end_idx]
        if "❯" in "\n".join(between_sep):
            body_lines, options = _extract_options(between_sep)
            if options:
                body = "\n".join(body_lines)
                body = re.sub(r'╌{10,}', SEPARATOR_DASHED, body)
                body = body.strip()
                return PermissionPrompt(options=options, body=body)

    # Fall back to after last separator (regular permission prompts)
    after_sep = lines[sep_indices[-1] + 1:]

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

    # Detect trust-related prompts (should not be auto-accepted)
    body_lower = body.lower()
    if "trust" in body_lower or "folder" in body_lower:
        return PermissionPrompt(options=options, body=body, prompt_type=PromptType.MCP_TRUST)

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


def parse_status_bar(output: str) -> StatusBar:
    """Parse Claude CLI status bar from tmux capture-pane output.

    Status bar is below the input box (after last ──── separator).
    """
    lines = output.split("\n")

    # Find last separator (bottom of input box)
    last_sep_idx = -1
    for i, line in enumerate(lines):
        if "─" * 10 in line:
            last_sep_idx = i

    # Get lines after last separator (status bar area)
    status_lines = lines[last_sep_idx + 1:] if last_sep_idx >= 0 else []
    status_text = "\n".join(status_lines)

    # Parse approval mode by emoji detection
    approval_mode: str | None = None
    if "⏵⏵" in status_text:
        approval_mode = "accept edits"
    elif "⏸" in status_text:
        approval_mode = "plan mode"
    # else: default mode (None)

    # Parse background tasks
    background_tasks = 0
    bg_match = re.search(r'(\d+)\s+background\s+tasks?', status_text)
    if bg_match:
        background_tasks = int(bg_match.group(1))

    # Parse context percentage
    context_percent: int | None = None
    ctx_match = re.search(r'auto-compact:\s*(\d+)%', status_text)
    if ctx_match:
        context_percent = int(ctx_match.group(1))

    return StatusBar(
        approval_mode=approval_mode,
        background_tasks=background_tasks,
        context_percent=context_percent,
    )


def parse_thinking_status(output: str) -> str | None:
    """Parse thinking status line from area just above input box.

    Formats vary:
    - ✶ Wibbling… (ctrl+c to interrupt · 30s · ↓ 914 tokens · thinking)
    - ✻ Cooked for 35s
    - ✽ Compacting conversation...

    Only looks at last 5 lines before first ──── separator to avoid
    picking up old thinking statuses from scrollback.

    Returns raw line with command injection:
    - 'ctrl+c to interrupt' → '/esc to interrupt'
    - 'esc to interrupt' → '/esc to interrupt'
    """
    lines = output.split("\n")

    # Find first ──── separator (top of input box)
    first_sep_idx = -1
    for i, line in enumerate(lines):
        if "─" * 10 in line:
            first_sep_idx = i
            break

    if first_sep_idx == -1:
        return None

    # Look at last 5 lines before separator (where thinking status appears)
    start_idx = max(0, first_sep_idx - 5)
    recent_lines = lines[start_idx:first_sep_idx]

    for line in recent_lines:
        stripped = line.strip()
        if stripped and stripped[0] in THINKING_SPINNERS:
            # THINKING_SPINNERS are unique enough - no content validation needed
            # Replace ctrl+c first, then esc (but only standalone, not /esc)
            result = stripped.replace("ctrl+c to interrupt", "/esc to interrupt")
            # Use regex to replace only standalone "esc to interrupt" (not "/esc")
            result = re.sub(r'(?<!/)(esc to interrupt)', r'/\1', result)
            return result
    return None


def parse_input_suggestion(output: str) -> str | None:
    """Parse suggestion from input box.

    Format: ❯ suggestion text                    ↵ send
    Located between last two ──── lines (input box).

    Returns suggestion text or None if no suggestion.
    """
    lines = output.split("\n")

    # Find last two ──── separators
    sep_indices = []
    for i, line in enumerate(lines):
        if "─" * 10 in line:
            sep_indices.append(i)

    if len(sep_indices) < 2:
        return None

    # Get content between last two separators
    start = sep_indices[-2]
    end = sep_indices[-1]

    content = "\n".join(lines[start + 1:end]).strip()

    # Match pattern: ❯ text ↵ send
    # \xa0 is non-breaking space that Claude uses
    match = re.match(r'❯[\s\xa0]*(.+?)[\s\xa0]*↵\s*send', content)
    if match:
        suggestion = match.group(1).strip()
        if suggestion:
            return suggestion

    return None
