# Bug: AskUserQuestion prompt not detected by permission_poller

**Date:** 2026-01-18
**Severity:** Medium
**Status:** Active

## Summary

`parse_screen()` returns `Idle` for AskUserQuestion prompts instead of `PermissionPrompt`. This causes the bot to not show the question with option buttons in Telegram.

## Root Cause

AskUserQuestion UI has **two** separators with options **between** them:

```
────────── (separator 1)
 ☐ Header

Question text?

❯ 1. Option 1        ← options HERE, between separators
  2. Option 2
  3. Type something.

────────── (separator 2)
  Chat about this    ← parser looks here (wrong!)

Enter to select · ↑/↓ to navigate
```

Current `parse_screen()` logic:
1. Find **last** separator
2. Look for options **after** it
3. Finds "Chat about this" → no options → returns `Idle`

## Expected Behavior

Parser should find options **between** two separators when they exist.

## Fix

In `screen.py`, change logic to:
1. Find all separators
2. If 2+ separators exist, look for options **between last two**
3. Fall back to "after last separator" for single-separator prompts

## Test Case

```python
def test_parse_askuserquestion_prompt():
    screen = '''
● Task completed

───────────────────────────────────────────────────────────────────────────────────────
 ☐ Test chat

Which option?

❯ 1. Option A
  2. Option B
  3. Type something.

───────────────────────────────────────────────────────────────────────────────────────
  Chat about this

Enter to select · ↑/↓ to navigate · Esc to cancel
'''
    result = parse_screen(screen)
    assert isinstance(result, PermissionPrompt)
    assert len(result.options) >= 2
    assert "Option A" in result.options[0]
```

## Related

- `src/codogram/screen.py` - `parse_screen()` function
- `src/codogram/permission_poller.py` - uses parse_screen
- Roadmap: "Claude's clarifying questions with option buttons"
