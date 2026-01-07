# Session Not Immediately Active After /start

**Date:** 2026-01-07
**Severity:** Medium
**Status:** Active

## Summary

After `/start` or `/branch`, there's a window (~1-2 minutes) where:
- Messages ARE sent to tmux
- But Claude's responses DON'T appear in Telegram

User thinks message didn't go through and sends again.

## Reproduction

1. `/branch group-to-supergroup` — creates thread, launches Claude
2. Immediately send message "Hello"
3. Message goes to tmux (confirmed in logs)
4. Claude responds
5. Response NOT visible in Telegram (watcher not running yet)
6. User sends message again
7. Eventually session binds, watcher starts, responses appear

## Timeline from logs

```
02:37:01 - /branch creates thread, launches Claude
02:37:01 - Poller starts (permission detection works)
02:38:29 - User sends message
02:38:29 - tmux_send executed (message delivered to tmux)
02:38:29 - Binding task started (searching for session_id)
           ← NO WATCHER YET, jsonl not monitored
02:39:29 - session_bound (found session_id after 1 minute)
02:39:29 - watcher started
02:39:34 - message_read: Claude's response finally visible
```

## Root Cause

Session binding (finding session_id in history.jsonl) takes time because:
1. Claude needs to process first message
2. Session appears in jsonl only after Claude responds
3. Binding polls every 0.5s but session might not exist yet

During this window, watcher is not started (needs session_id).

## Impact

- User confusion: "message didn't send"
- Duplicate messages sent
- Poor UX on first interaction after /start

## Proposed Fix

**Option A: Queue messages until ready**
- Cache user messages while `awaiting_new_session=True`
- Send all cached messages when session binds
- Show "⏳ Connecting..." feedback

**Option B: Start watcher earlier**
- Start watcher immediately with project cwd
- Let watcher find session dynamically
- More complex but faster feedback

**Option C: Visual feedback only**
- Show "Message queued, connecting to Claude..."
- User knows message is pending
- Simplest fix

## Related

- Bug: MCP trust prompt (2026-01-07) — compounds this issue
