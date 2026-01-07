# MCP Trust Prompt Support

**Date:** 2026-01-07
**Status:** Design approved (v2 — with PromptType enum)

## Problem

When Claude shows MCP server trust prompt, `permission_poller` doesn't detect it. Bot sends `C-c` before user messages, which triggers "Press Ctrl-C again to exit" and breaks the session.

## Solution

Detect MCP trust prompts (box-style UI) and show them in Telegram as regular permission prompts, but skip auto-accept.

## Key Decisions

1. **Full integration** — show as permission prompt with buttons in Telegram
2. **No auto-accept** — MCP trust prompts always require manual confirmation
3. **Same response mechanism** — send option number to tmux (like regular prompts)
4. **Same display** — no visual distinction from regular permission prompts
5. **PromptType enum** — extensible type system instead of boolean flags

## MCP Prompt Format

```
╭──────────────────────────────────────────────────────────────────────╮
│ New MCP server found in .mcp.json: telegram                         │
│ ...                                                                  │
│ ❯ 1. Use this and all future MCP servers in this project            │
│   2. Use this MCP server                                            │
│   3. Continue without using this MCP server                         │
╰──────────────────────────────────────────────────────────────────────╯
   Enter to confirm · Esc to reject
```

Key differences from regular prompts:
- Box characters `╭╮╯╰` instead of `────` separator
- `│` on sides of each line
- `❯` and options INSIDE the box
- Footer outside the box

## Implementation

### 1. screen.py — Data model

Add `PromptType` enum:
```python
class PromptType(Enum):
    REGULAR = "regular"
    MCP_TRUST = "mcp_trust"
    # Future: TRUST_FOLDER, API_KEY, etc.
```

Update `PermissionPrompt` dataclass:
```python
@dataclass
class PermissionPrompt:
    options: list[str]
    body: str = ""
    prompt_type: PromptType = PromptType.REGULAR
```

### 2. screen.py — Refactor option extraction (DRY)

Extract common logic into `_extract_options()`:
```python
def _extract_options(lines: list[str]) -> tuple[list[str], list[str]]:
    """Extract options from lines containing ❯ selector.

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
            # NOTE: \s{2,} (2+ spaces) — NOT \s* — to avoid false positives
            match = re.match(r'\s{2,}(\d+\.\s+.+)', line)
            if match:
                options.append(match.group(1).strip())
            elif line.strip().startswith(("Esc", "Enter")):
                break
        else:
            body_lines.append(line)

    return body_lines, options
```

Use in `parse_screen()`, `_parse_options_without_separator()`, and `_parse_mcp_trust_prompt()`.

### 3. screen.py — MCP prompt parsing

Add `_parse_mcp_trust_prompt()` function:
```python
def _parse_mcp_trust_prompt(lines: list[str]) -> PermissionPrompt | None:
    """Parse MCP server trust prompt (box-style UI).

    Format:
    ╭────────────────────────────────╮
    │ New MCP server found...        │
    │ ❯ 1. Use this and all future   │
    │   2. Use this MCP server       │
    ╰────────────────────────────────╯
       Enter to confirm · Esc to reject
    """
    # Find box boundaries
    box_start = None
    box_end = None
    for i, line in enumerate(lines):
        if "╭" in line and box_start is None:
            box_start = i
        if "╰" in line:
            box_end = i

    if box_start is None or box_end is None:
        return None

    # Extract content between │...│
    content_lines = []
    for line in lines[box_start + 1 : box_end]:
        # Strip │ from sides
        stripped = re.sub(r'^[^│]*│(.*)│[^│]*$', r'\1', line)
        content_lines.append(stripped.strip())

    body_lines, options = _extract_options(content_lines)

    if not options:
        return None

    body = "\n".join(body_lines).strip()
    return PermissionPrompt(
        options=options,
        body=body,
        prompt_type=PromptType.MCP_TRUST
    )
```

### 4. screen.py — Parsing order

Update `parse_screen()` with documented order:
```python
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

    # 2-5. Existing logic...
```

### 5. auto_accept.py — Bypass by type

Update `try_auto_accept()` signature:
```python
async def try_auto_accept(
    options: list[str],
    body: str,
    tmux: TmuxSession,
    ...,
    prompt_type: PromptType = PromptType.REGULAR,
) -> bool:
```

Check against whitelist:
```python
# Only auto-accept regular prompts
AUTO_ACCEPT_TYPES = {PromptType.REGULAR}

if prompt_type not in AUTO_ACCEPT_TYPES:
    logger.debug(f"Auto-accept: skipping {prompt_type.value} prompt")
    return False
```

### 6. permission_poller.py — Pass type

```python
if await try_auto_accept(
    parsed.options, parsed.body, tmux,
    ...,
    prompt_type=parsed.prompt_type,
):
```

## Edge Cases

1. **False positives** — user outputs box in code
   - Solution: require `❯` with numbered options inside box
   - Without `❯ 1.` — not an MCP prompt

2. **Partial render** — box not fully drawn yet
   - Solution: require closing `╰` before parsing
   - Debounce in poller already gives time for render

3. **Multiple boxes on screen** — scrollback with previous ones
   - Solution: parse only the last box (find last `╭` and `╰`)

4. **Multiple MCP servers** — sequential prompts for each server
   - Current logic handles this (one prompt at a time)
   - Each dismissed, next appears

5. **MCP prompt + regular prompt simultaneously** — unlikely
   - MCP parsed first (more specific), takes priority

## Files Changed

- `src/codogram/screen.py` — PromptType enum, MCP parsing, _extract_options()
- `src/codogram/auto_accept.py` — check prompt_type
- `src/codogram/permission_poller.py` — pass prompt_type

## Testing

### Unit tests for screen.py
- `test_parse_mcp_trust_prompt_basic` — standard MCP prompt
- `test_parse_mcp_trust_prompt_type` — verify `prompt_type=MCP_TRUST`
- `test_parse_mcp_trust_prompt_incomplete` — without `╰` returns `Idle`
- `test_parse_mcp_trust_prompt_no_options` — box without `❯` returns `Idle`
- `test_parse_mcp_trust_prompt_last_box` — multiple boxes, takes last
- `test_regular_prompt_type` — regular prompt has `prompt_type=REGULAR`
- `test_extract_options_reusable` — _extract_options works standalone

### E2E test
- Add to `docs/e2e/commands/permissions.md`
- Requires project with `.mcp.json`

## Related

- Bug: [2026-01-07-mcp-trust-prompt-not-detected.md](../bugs/active/2026-01-07-mcp-trust-prompt-not-detected.md)
- ROADMAP: "MCP trust prompt support"
