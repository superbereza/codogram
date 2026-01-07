# MCP Trust Prompt Not Detected

**Date:** 2026-01-07
**Severity:** High
**Status:** Active

## Summary

When Claude shows MCP server trust prompt, permission_poller doesn't detect it. Messages sent during this prompt are lost (go to shell instead of Claude).

## Reproduction

1. Create new thread/branch in project with `.mcp.json`
2. `/start` launches Claude
3. Claude shows MCP trust prompt:
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
4. User sends message in Telegram
5. Bot sends `C-c` + text + `Enter` to tmux
6. `C-c` triggers "Press Ctrl-C again to exit"
7. Text goes to shell, not Claude

## Root Cause

1. `screen.py` parser doesn't recognize MCP trust prompt format
2. Bot sends `C-c` before every message (to clear input line)
3. `C-c` in MCP prompt context = exit Claude

## Evidence

From `logs/tmux-send-debug.log`:
```
2026-01-07 02:38:29.673 BEFORE:
│ ❯ 1. Use this and all future MCP servers in this project │
   Enter to confirm · Esc to reject

2026-01-07 02:38:29.733 AFTER C-c:
   Press Ctrl-C again to exit
```

## Impact

- First message after `/start` in MCP-enabled project is lost
- User has to send message twice
- No indication of what happened

## Proposed Fix

1. Add MCP trust prompt detection to `screen.py`
2. Show as permission prompt with options in Telegram
3. Don't send `C-c` when MCP prompt is active (or handle differently)

## Related

- ROADMAP: "Поддержка MCP trust prompt"
- Previous failed attempt: 2026-01-04 (broke detection everywhere)
