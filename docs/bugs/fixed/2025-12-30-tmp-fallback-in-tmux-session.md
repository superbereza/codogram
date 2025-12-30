# Bug: /tmp fallback in TmuxSession creation

**Status:** Fixed
**Date:** 2025-12-30

## Problem

Multiple places use `/tmp` as fallback when `project.cwd` is None:

```python
tmux = TmuxSession(tmux_name, project.cwd or "/tmp")
```

This is wrong because:
1. If `cwd = None` something is broken, should fail explicitly
2. Claude session in `/tmp` is meaningless
3. Masks real bugs

## Locations

- `bot.py:97` - `get_tmux_for_chat()`
- `bot.py:101` - legacy fallback
- `bot.py:834` - `/esc` command
- `bot.py:1077` - permission callback
- `tmux.py:162` - `find_tmux_session()` (this one might be ok for existence check)

## Solution

1. Remove `or "/tmp"` fallback
2. Add explicit check that cwd is set
3. For worktree topics use `thread.worktree_path or project.cwd`

## Related

- Git worktree support needs correct cwd handling
