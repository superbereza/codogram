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
context left until autocompact: 12%
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

1. Find last `────` separator line
2. Look for lines after it containing approval mode indicators (`⏵⏵`, `⏸`) or `background task`
3. Look for `Context left until` pattern
4. If generating (has `· Hatching…` above input), status bar shows different content — skip parsing

### Data Model

```python
@dataclass
class StatusBar:
    approval_mode: str | None  # "accept edits", "plan mode", None (default)
    background_tasks: int      # 0, 1, 2...
    context_percent: int | None  # 0-100 or None if not displayed
```

## Implementation

### New Files

- `src/codogram/handlers/shift_tab.py` — handler for `/shift_tab`

### Modified Files

- `src/codogram/screen.py` — add `parse_status_bar()` function
- `src/codogram/handlers/settings.py` — enhance `/settings` to show session state
- `src/codogram/tmux.py` — add `send_shift_tab()` method

### Flow

**`/shift_tab`:**
1. Get tmux session for current thread/project
2. Send `S-Tab` key via tmux send-keys
3. Wait 200ms for UI to update
4. Capture pane and parse status bar
5. Send new approval mode to Telegram

**`/settings`:**
1. Capture tmux pane
2. Parse status bar
3. Format and send to Telegram

## Out of Scope

- Generation indicator (`· Hatching…`) — separate feature "Activity indicators"
- Model indicator — not shown in status bar
