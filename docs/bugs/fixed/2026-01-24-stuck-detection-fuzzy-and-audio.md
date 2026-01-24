# Bug: Stuck detection fails with extra chars or audio messages

**Date:** 2026-01-24
**Severity:** Medium
**Status:** Fixed
**Commit:** d612fdc

## Summary

Two related issues in stuck message detection:

1. **Extra characters**: Sometimes keypresses insert extra chars (e.g., "1") at the beginning of input, breaking the `startswith` comparison
2. **Audio messages**: Voice/audio messages set `last_sent_message` to file path info instead of transcribed text, so comparison always failed

## Reproduction steps

### Extra characters
1. Send a message to Claude
2. Some keypress inserts "1" at the start of input (race condition)
3. Input shows: `1Hello world` instead of `Hello world`
4. Stuck detection compares `Hello world`.startswith(`1Hello world`) = False
5. Message never detected as stuck

### Audio messages
1. Send a voice message
2. Whisper transcribes it to "Hello world"
3. `last_sent_message` was not set (or was set to audio file info)
4. Stuck detection has nothing to compare against
5. Transcribed text sits in input forever

## Root cause

### Extra characters
Only used `startswith` comparison which fails if input has extra prefix:
```python
first_line.startswith(input_text)  # "Hello".startswith("1Hello") = False
```

### Audio messages
`audio.py` handler didn't set `last_sent_message` after transcription.

## Fix

### Fuzzy matching
Added bidirectional `in` checks to handle extra characters:
```python
is_potentially_stuck = (
    PASTED_PATTERN.match(input_text) is not None or
    (first_line is not None and (
        first_line.startswith(input_text) or
        input_text in first_line or      # "Hello" in "1Hello" = True
        first_line in input_text          # "Hello" in "Hello1" = True
    ))
)
```

### Audio tracking
Added `last_sent_message` assignment in audio handler:
```python
# Track for stuck message detection
if result.thread:
    result.thread.last_sent_message = text  # transcribed text

# Send to tmux
_message_router.send_to_tmux(result, text)
```

## Affected code

- `src/codogram/claude/poller/processors/stuck.py` - fuzzy matching logic
- `src/codogram/handlers/audio.py` - last_sent_message tracking
