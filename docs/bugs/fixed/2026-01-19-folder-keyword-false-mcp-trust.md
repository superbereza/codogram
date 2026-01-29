# False MCP_TRUST detection on "folder" keyword in Bash commands

**Date:** 2026-01-19
**Status:** Active
**Severity:** Medium (auto-accept skipped unexpectedly)

## Summary

Auto-accept skips Bash command prompts that contain the word "folder" in description, incorrectly classifying them as `MCP_TRUST` prompts.

## Reproduction

1. Enable auto_accept for a thread
2. Run a Bash command with "folder" in description:
   ```
   mv docs/plans/file.md docs/plans/done/
   Move design and plan to done folder
   ```
3. Expected: auto-accept triggers, sends "1"
4. Actual: prompt sent to Telegram, log shows "Auto-accept: skipping mcp_trust prompt"

## Root Cause

`screen.py` lines 206-209 and 226-229:
```python
if "trust" in body_lower or "folder" in body_lower:
    return PermissionPrompt(options=options, body=body, prompt_type=PromptType.MCP_TRUST)
```

This check is too broad - "folder" can appear in regular Bash command descriptions.

## Evidence

```
2026-01-19 00:38:26 [DEBUG] Thread poller [users-in-group-registration] IDLE->DEBOUNCING:
    options=['1. Yes', '2. Yes, and always allow access to plans/ from this project', '3. No']
2026-01-19 00:38:27 [DEBUG] Auto-accept: skipping mcp_trust prompt
2026-01-19 00:38:27 [DEBUG] DEBOUNCING->SHOWING: sending to Telegram
```

Screen content:
```
Bash command
   mv .../docs/plans/2026-01-18-group-authorization-design.md .../docs/plans/done/
   Move design and plan to done folder    <-- "folder" triggers false positive

❯ 1. Yes
  2. Yes, and always allow access to plans/ from this project
  3. No
```

## Potential Fixes

1. **Check options instead of body** - MCP/folder trust prompts have specific options:
   - MCP: "Use this MCP server", "Use this and all future MCP servers"
   - Folder trust: "Always allow", "Trust this folder"
   - Regular: "Yes", "No"

2. **More specific phrases** - Instead of just "folder", check for:
   - "trust this folder"
   - "folder access"
   - "allow access to folder"

3. **Check prompt structure** - Trust prompts have different structure than Bash prompts

## Files

- `src/codogram/screen.py:206-209` - Regular prompt detection
- `src/codogram/screen.py:226-229` - No-separator prompt detection
- `src/codogram/auto_accept.py:60-62` - Where skip happens
