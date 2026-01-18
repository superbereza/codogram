# Bug: Stuck detection didn't work for General (null thread) in project-level poller

**Date:** 2026-01-18
**Severity:** High
**Status:** Fixed
**Commit:** TBD

## Summary

Messages in General topic (thread_id=None) were never detected as stuck because the project-level poller received `thread=None` as parameter, not the actual ThreadInfo object.

## Reproduction steps

1. Send a message to General topic (no thread_id)
2. Message gets pasted into Claude input but Enter not pressed
3. Message sits in input indefinitely
4. Stuck detection never triggers

## Root cause

Two different representations of "null thread":

1. **In messages.py**: `result.thread` is the actual `ThreadInfo` object from `project.threads[None]`
   - `last_sent_message` is set here correctly

2. **In permission_poller**: `thread` parameter is `None` (not the ThreadInfo object)
   - Code did: `last_msg = thread.last_sent_message if thread else None`
   - Since `thread is None`, `last_msg` was always `None`

The poller was created with `thread=None`:
```python
async def create_poller_task(bot, project, telegram_queue):
    return asyncio.create_task(permission_poller(bot, project, telegram_queue, thread=None))
```

But `last_sent_message` was stored in `project.threads[None].last_sent_message`.

## Fix

Get the actual thread object from project when `thread` parameter is None:

```python
# For project-level poller (thread=None), get the null thread from project
effective_thread = thread if thread else project.threads.get(None)
last_msg = effective_thread.last_sent_message if effective_thread else None
```

Also updated the clearing logic to use `effective_thread`.

## Affected code

- `src/codogram/permission_poller.py:371-373` - get effective_thread
- `src/codogram/permission_poller.py:396-397` - clear last_sent_message
