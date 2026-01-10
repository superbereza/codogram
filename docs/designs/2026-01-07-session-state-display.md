# Session State Display & Control

## Summary

Display Claude session state in Telegram and allow mode cycling via `/shift_tab` command.

## Commands

### `/shift_tab`

Send Shift+Tab to tmux, cycling approval mode. Show new mode:

```
⏵⏵ accept edits on
```

or:

```
⏸ plan mode on
```

or:

```
default mode on
```

### `/settings` (enhanced)

Show current session state:

```
⏵⏵ accept edits on, (/shift_tab to cycle)
no background tasks
context left until autocompact: 45%
```

Variations:

```
⏸ plan mode on, (/shift_tab to cycle)
1 background task
context left until autocompact: not displayed
```

```
default mode on, (/shift_tab to cycle)
2 background tasks
context left until autocompact: 0%
```

## Status Bar Parsing

Parse line BELOW input box in tmux capture-pane (only visible in idle state).

### Layout

```
──────────────────────────────────────────────────────────────────────
> [input]
──────────────────────────────────────────────────────────────────────
  ⏵⏵ accept edits on · 1 background task     Context left until
  (shift+tab to cycle)                        auto-compact: 45%
```

### Components

**Approval mode** (left side):
- `⏵⏵ accept edits on` — auto-accept edits
- `⏸ plan mode on` — plan mode enabled
- (empty) — default mode, no indicator shown

**Background tasks** (middle, after `·`):
- `1 background task` / `N background tasks`
- Not shown if 0

**Context** (right side):
- `Context left until auto-compact: X%`
- May not be displayed

### Parsing Strategy

1. Find last `────` separator line (bottom of input box)
2. Look at lines BELOW this separator for status bar
3. Parse by emoji detection (more robust than text matching):
   - `⏵⏵` (U+23F5 x2) → "accept edits" mode
   - `⏸` (U+23F8) → "plan mode"
   - Neither → "default" mode
4. Background tasks: regex `(\d+) background tasks?`
5. Context: regex `auto-compact:\s*(\d+)%`

Note: Two separators exist around input box. Status bar is below the LAST separator.

### Data Model

```python
@dataclass
class StatusBar:
    approval_mode: str | None  # "accept edits", "plan mode", None (default)
    background_tasks: int      # 0, 1, 2...
    context_percent: int | None  # 0-100 or None if not displayed
```

## Error Handling

### Tmux not running

If tmux session doesn't exist:
- `/shift_tab`: "tmux session not found"
- `/settings`: "tmux session not found"

### Claude is busy (generating)

During generation, status bar shows `? for shortcuts` or just background tasks count.
Approval mode is not visible.

Response:
- `/settings`: show what we could parse, "approval mode: not displayed" for missing data
- `/shift_tab`: send key anyway, but may not be able to confirm new mode

### Parse failure

If nothing could be parsed from status bar:
- Show "could not parse status bar"

## Thread/Project Context

In forum mode, each thread has its own tmux session.

- Use `thread.get_tmux_session(project_name)` for threads
- Use `project.tmux_session` for simple mode
- Same logic as `permission_poller.py`

## Implementation

### Architecture

Following layered architecture:
- **Handler** (`handlers/shift_tab.py`): thin router, delegates to service
- **Service** (`services/session_state.py`): business logic for parsing and commands
- **Domain** (`screen.py`): pure parsing function `parse_status_bar()`

### New Files

- `src/codogram/handlers/shift_tab.py` — handler for `/shift_tab`
- `src/codogram/services/session_state.py` — business logic

### Modified Files

- `src/codogram/screen.py` — add `parse_status_bar()` function
- `src/codogram/handlers/settings.py` — enhance `/settings` to show session state

### Flow

**`/shift_tab`:**
1. Get tmux session for current thread/project
2. If tmux doesn't exist → return error
3. Capture pane, parse current approval mode (save as `old_mode`)
4. Send `S-Tab` key via `tmux.send_key("S-Tab")`
5. Wait 200ms, capture pane, parse new mode
6. If mode == `old_mode` → wait 200ms more, parse again (ONE retry only)
7. Show result:
   - If mode changed → show new mode
   - If mode still same after retry → show "mode: {current}" (what we parsed, even if same)

**`/settings`:**
1. Get tmux session for current thread/project
2. If tmux doesn't exist → return error
3. Capture pane and parse status bar
4. Format response:
   - approval mode (or "not displayed")
   - background tasks count
   - context percent (or "not displayed")
5. Send to Telegram

## Out of Scope

- Generation indicator (`· Hatching…`) — separate feature "Activity indicators"
- Model indicator — not shown in status bar
