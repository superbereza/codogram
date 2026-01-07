# MCP Trust Prompt Support

**Date:** 2026-01-07
**Status:** Design approved

## Problem

When Claude shows MCP server trust prompt, `permission_poller` doesn't detect it. Bot sends `C-c` before user messages, which triggers "Press Ctrl-C again to exit" and breaks the session.

## Solution

Detect MCP trust prompts (box-style UI) and show them in Telegram as regular permission prompts, but skip auto-accept.

## Key Decisions

1. **Full integration** — show as permission prompt with buttons in Telegram
2. **No auto-accept** — MCP trust prompts always require manual confirmation
3. **Same response mechanism** — send option number to tmux (like regular prompts)
4. **Same display** — no visual distinction from regular permission prompts
5. **Flag-based identification** — `is_mcp_trust: bool` in `PermissionPrompt` dataclass

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

### 1. screen.py — Parsing

Update `PermissionPrompt` dataclass:
```python
@dataclass
class PermissionPrompt:
    options: list[str]
    body: str = ""
    is_mcp_trust: bool = False  # NEW
```

Add `_parse_mcp_trust_prompt()` function:
- Look for `╭` at line start (box opening)
- Collect lines between `│...│`
- Extract body (before `❯`) and options (after `❯`)
- Return `PermissionPrompt(is_mcp_trust=True)`

In `parse_screen()` — call `_parse_mcp_trust_prompt()` first, before looking for `────`.

### 2. auto_accept.py — Bypass

Update `try_auto_accept()` signature:
```python
async def try_auto_accept(
    options: list[str],
    body: str,
    tmux: TmuxSession,
    ...,
    is_mcp_trust: bool = False,  # NEW
) -> bool:
```

Early return at function start:
```python
if is_mcp_trust:
    logger.debug("Auto-accept: skipping MCP trust prompt")
    return False
```

### 3. permission_poller.py — Pass flag

```python
if await try_auto_accept(
    parsed.options, parsed.body, tmux,
    ...,
    is_mcp_trust=parsed.is_mcp_trust,  # NEW
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
   - Solution: parse only the last box (closer to screen end)

## Files Changed

- `src/codogram/screen.py` — MCP prompt parsing
- `src/codogram/auto_accept.py` — skip MCP prompts
- `src/codogram/permission_poller.py` — pass flag

## Testing

### Unit tests for screen.py
- `test_parse_mcp_trust_prompt_basic` — standard MCP prompt
- `test_parse_mcp_trust_prompt_sets_flag` — verify `is_mcp_trust=True`
- `test_parse_mcp_trust_prompt_incomplete` — without `╰` returns `Idle`
- `test_parse_mcp_trust_prompt_no_options` — box without `❯` returns `Idle`
- `test_regular_prompt_not_mcp` — regular prompt has `is_mcp_trust=False`

### E2E test
- Add to `docs/e2e/commands/permissions.md`
- Requires project with `.mcp.json`

## Related

- Bug: [2026-01-07-mcp-trust-prompt-not-detected.md](../bugs/active/2026-01-07-mcp-trust-prompt-not-detected.md)
- ROADMAP: "MCP trust prompt support"
