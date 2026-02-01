# Bug: Subagent message lost due to race condition

**Date:** 2026-02-01
**Severity:** Medium
**Status:** Fix implemented, needs testing

## Summary

Message from Claude was displayed on tmux screen but never sent to Telegram. The message existed in subagent file but watcher didn't process it.

## Root Cause

Race condition in `_check_subagents()`:

```python
# OLD CODE (buggy):
for filepath in files:
    if filepath.name in self.seen_subagent_files:
        continue

    self.seen_subagent_files.add(filepath.name)  # <- BEFORE extraction!

    text = self._extract_subagent_text(filepath)
    if text:
        # send
```

File was added to `seen_subagent_files` BEFORE extraction attempt. If file was empty/incomplete at that moment, extraction failed and file was never retried.

## Timeline of the bug

```
03:28:58 - ff6731.jsonl processed successfully
03:29:21.183 - 706848.jsonl created (Birth time)
03:29:21.xxx - Watcher poll: sees file, adds to seen, tries to read
03:29:21.xxx - Line 1 empty or incomplete -> extraction fails
03:29:26.345 - Claude finishes writing file (Modify time)
03:29:xx - All subsequent polls skip file (already in seen)
03:32:15 - User notices message not sent
```

## Evidence

1. File `706848.jsonl` contains valid message:
   ```
   Line 1: Assistant "Не могу проверить со своей стороны..."
   Line 2: User (suggestion system prompt)
   Line 3: Assistant thinking
   Line 4: Assistant suggestion "/mcp"
   ```

2. 5-second gap between Birth (03:29:21) and Modify (03:29:26) confirms file was written incrementally

3. No `subagent_text: file=706848` in logs - file was never processed

4. Previous file `ff6731.jsonl` was processed at 03:28:58 - watcher was running

## Fix

Moved `seen_subagent_files.add()` to AFTER extraction, with retry logic:

```python
# NEW CODE:
is_ready, text = self._extract_subagent_text(filepath)

if not is_ready:
    # File not ready (empty/invalid JSON), retry on next poll
    continue

# File is ready, mark as seen
self.seen_subagent_files.add(filepath.name)
```

Return values:
- `is_ready=False` -> file empty/incomplete -> retry on next poll
- `is_ready=True, text=None` -> valid JSON but wrong format -> skip, mark seen
- `is_ready=True, text="..."` -> success -> send, mark seen

## Additional changes

1. Added git revision to startup log for easier debugging
2. Added detailed logging in `_check_subagents()`:
   - `subagent_glob: found=X seen=Y`
   - `subagent_new: file=...`
   - `subagent_text: file=... len=...`
   - `subagent_skip: file=... (no text)`
   - `subagent_empty/incomplete/not_assistant/etc.`

## Files changed

- `src/codogram/main.py` - added `get_git_revision()` and startup log
- `src/codogram/claude/history_watcher.py` - fixed race condition, added logging
- `src/codogram/tmux/session.py` - removed heavy debug logging to file (was filling disk)

## Testing

Needs real-world testing to confirm fix works. Watch for:
1. `subagent_new` logs when new files appear
2. `subagent_text` logs when messages are sent
3. No more lost messages

## Related

- `docs/bugs/active/2026-01-29-message-lost-during-accept-edits.md` - different bug (tmux input issue)
