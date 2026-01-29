# Bug: Stuck detection fails for long lines wrapped by tmux

**Date:** 2026-01-21
**Severity:** High
**Status:** Fixed
**Commit:** 0e90727

## Summary

Messages with long first lines (>80 characters) were never detected as stuck because tmux wraps long lines, causing a mismatch between `input_text` and `last_sent_message`.

## Reproduction steps

1. Send a message with first line longer than tmux width (~80-120 chars)
2. Message gets pasted into Claude input but Enter not pressed
3. Message sits in input indefinitely
4. Stuck detection never triggers

## Root cause

Tmux wraps long lines to fit the terminal width. When a message's first line is 174 characters:

- `last_sent_message.split('\n')[0]` = full 174 character line
- `extract_input_text()` = only ~80 characters (what fits in one tmux line after `❯`)

The comparison used `==` which required exact match:
```python
input_text == last_msg.split('\n')[0]  # "Let's create...cheaper?" != "Let's create...tips:"
```

## Example

Message first line: `Let's create a text box or a speech bubble with a message like "How can you make your cart cheaper?" — when you click this button, a larger text/modal window opens with tips:` (174 chars)

- `last_msg.split('\n')[0]` = full 174 chars
- `input_text` from tmux = first ~80 chars only
- They don't match → stuck not detected

## Fix

Changed comparison from `==` to `startswith`:

```python
first_line = last_msg.split('\n')[0] if last_msg else None
is_potentially_stuck = (
    PASTED_PATTERN.match(input_text) is not None or
    (first_line is not None and first_line.startswith(input_text))
)
```

## Affected code

- `src/codogram/permission_poller.py:376-382` - stuck detection comparison
