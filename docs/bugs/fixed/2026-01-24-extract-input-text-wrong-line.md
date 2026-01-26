# Bug: extract_input_text returns first prompt line instead of last

**Date:** 2026-01-24
**Severity:** High
**Status:** Fixed
**Commit:** 1d2f660

## Summary

`extract_input_text()` returned the first line starting with `❯` in the tmux screen, but in scrollback scenarios this could be an old prompt, not the current input. Stuck detection compared against stale text and failed.

## Reproduction steps

1. Have a tmux session with scrollback containing old prompts
2. Send a message to Claude
3. Message gets pasted but Enter not pressed
4. Screen shows multiple `❯` lines - old ones in scrollback, current one at bottom
5. Stuck detection picks up the wrong (first) line

## Root cause

The function iterated through lines and returned on first match:

```python
def extract_input_text(screen: str) -> str | None:
    for line in screen.split("\n"):
        stripped = line.strip()
        if stripped.startswith("❯"):
            text = stripped[1:].strip()
            if text:
                return text  # Returns FIRST match
    return None
```

## Fix

Changed to collect all matches and return the last one:

```python
def extract_input_text(screen: str) -> str | None:
    result = None
    for line in screen.split("\n"):
        stripped = line.strip()
        if stripped.startswith("❯"):
            text = stripped[1:].strip()
            if text:
                result = text  # Keep iterating
    return result  # Return LAST match
```

## Affected code

- `src/codogram/claude/screen.py` - `extract_input_text()` function
