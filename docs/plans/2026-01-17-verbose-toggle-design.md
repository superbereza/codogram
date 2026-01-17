# Verbose Toggle Design

## Summary

Add short/long display mode for tool calls, permissions, and auto-accept messages. Short mode shows first 5 lines, long mode shows full content.

## Data Model

New fields:

```python
# In ThreadInfo
verbose: bool = False  # False = short (default), True = long/full

# In ProjectState
verbose: bool = False  # for main thread / simple mode
```

Per-thread setting, same pattern as `auto_accept`.

## `/settings` Output

```
switch-full-short-claude-statuses

chat
• auto-accept: ○ off
• verbose: ○ off

claude
• mode: default
• background tasks: 0
• context: 85%
```

With inline keyboard (vertical):
```
[/auto_accept]
[/verbose]
[/shift_tab]
```

## Commands

### `/verbose`

Toggle verbose mode for current context (thread or project).

Response:
```
Verbose output: ● on
```
or
```
Verbose output: ○ off
```

### `/auto_accept`

Existing command, update response format:
```
Auto-accept: ● on
```
or
```
Auto-accept: ○ off
```

## Short/Long Display Logic

### Where applied:
1. Permission prompts (`permission_poller.py` - body)
2. Tool calls (`watcher.py` - body)
3. Auto-accept messages

### Short mode (default):
- Show first 5 lines of body
- Add `...` if truncated

### Long mode (verbose: on):
- Show full body (current behavior)

### Example (short):
```
● Edit `src/config.py`
────────────
  auto_accept: bool = False
  verbose: bool = False
+ display_mode: str = "short"
...
```

## Inline Buttons

Buttons in `/settings` message:
- `/auto_accept` - toggles auto-accept, updates message
- `/verbose` - toggles verbose, updates message
- `/shift_tab` - sends Shift+Tab to tmux, updates message

Arranged vertically in same order as text.

Callback data format:
- `settings:auto_accept:{tmux_name}`
- `settings:verbose:{tmux_name}`
- `settings:mode:{tmux_name}`

## Files to Modify

1. `src/codogram/session_manager.py` - add `verbose` field to ThreadInfo and ProjectState
2. `src/codogram/handlers/settings.py` - update `/settings` output, add `/verbose` command
3. `src/codogram/keyboards/` - add settings keyboard builder
4. `src/codogram/handlers/callbacks.py` - handle settings button callbacks
5. `src/codogram/watcher.py` - apply short/long logic to tool calls
6. `src/codogram/permission_poller.py` - apply short/long logic to permissions
7. `src/codogram/auto_accept.py` - apply short/long logic to auto-accept messages
