# Bug: AskUserQuestion prompt not detected by permission_poller

**Date:** 2026-01-18
**Severity:** Medium
**Status:** Active - fix caused regression

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

## Attempted Fix (reverted)

**Commit:** f0c4816 (reverted in c975ff6)

Changed `parse_screen()` logic to look for options **between** last two separators when 2+ exist:

```python
# Added to parse_screen():
if len(sep_indices) >= 2:
    # Try between last two separators first (AskUserQuestion format)
    start_idx = sep_indices[-2]
    end_idx = sep_indices[-1]
    between_sep = lines[start_idx + 1:end_idx]
    if "❯" in "\n".join(between_sep):
        body_lines, options = _extract_options(between_sep)
        if options:
            return PermissionPrompt(options=options, body=body)
```

**Problem:** This broke regular permission prompts. When Claude shows a normal permission prompt, the screen often has 2+ separators (from previous output + current prompt). The fix incorrectly looked between old separators instead of after the last one.

**Symptom:** Permission poller stopped detecting ANY prompts, bot became unresponsive.

## Next Steps

Need more careful fix that:
1. Only applies between-separator logic for AskUserQuestion format specifically
2. Doesn't break regular permission prompts (options after single separator)

Possible approach: detect AskUserQuestion by unique markers like `☐` header or "Chat about this" footer.

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
```

## Related

- `src/codogram/screen.py` - `parse_screen()` function
- `src/codogram/permission_poller.py` - uses parse_screen
- Roadmap: "Claude's clarifying questions with option buttons"
