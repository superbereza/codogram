# Design: /settings in DM for Global Defaults

## Overview

Command `/settings` in DM with the bot to configure global defaults for all projects.

**Hierarchy:** Global → Thread (two levels)
- Global defaults stored in `config.json["global_defaults"]`
- Thread stores only overrides
- Reading: `thread.setting ?? global.setting`
- Command `/reset_to_default` clears overrides

## Data Model

**config.json structure:**
```json
{
  "projects": { ... },
  "users": { ... },
  "global_defaults": {
    "auto_accept": false,
    "response_mode": "all",
    "display_mode": "lines",
    "line_limit": 5,
    "display_bullet": true,
    "display_thinking_text": false,
    "working_status": false,
    "feat_suggestions": false,
    "feat_avatar_pack": false
  }
}
```

**Hardcoded defaults (fallback when no global_defaults):**
```python
HARDCODED_DEFAULTS = {
    "auto_accept": False,
    "response_mode": "all",
    "display_mode": "lines",
    "line_limit": 5,
    "display_bullet": True,
    "display_thinking_text": False,
    "working_status": False,
    "feat_suggestions": False,
    "feat_avatar_pack": False,
}
```

## UX

### `/settings` in DM

Shows same sections as in group, but without "claude" (no session).

```
Global defaults

chat
• auto-accept: ○ off
• response-mode: all

ui
• verbose-mode: lines (5)
• display-bullet: ● on
• display-thinking: ○ off

experimental
• working-status: ○ off
• suggestions: ○ off
• avatar-pack: ○ off

/reset_to_default — reset to factory defaults

[/auto_accept] [/response_mode]
[◀] [Close] [▶]
```

### `/settings` in group

Behavior unchanged. Shows effective values (thread override ?? global).
User doesn't see difference between inherited and overridden.

```
Project: codogram

chat
• auto-accept: ○ off
• response-mode: all

claude
• mode: default
...

ui
...

/reset_to_default — reset to global defaults

[/auto_accept] [/response_mode]
[◀] [Close] [▶]
```

### `/reset_to_default` command

**In group/thread:**
- Resets only current thread to global defaults
- Clears all overrides in thread (fields → None)
- Confirmation: "Reset this thread to global defaults? [Yes] [No]"
- After: "Thread reset to global defaults"

**In DM:**
- Resets ALL threads in ALL projects to global defaults
- Clears all overrides everywhere
- Confirmation: "Reset ALL threads to global defaults? [Yes] [No]"
- After: "All threads reset to global defaults"

## Technical Implementation

### New functions in `config.py`

```python
HARDCODED_DEFAULTS = { ... }

def get_global_defaults() -> dict:
    """Load global defaults or return hardcoded defaults."""
    config = load_config()
    return config.get("global_defaults", HARDCODED_DEFAULTS)

def set_global_default(key: str, value: Any) -> None:
    """Update a single global default."""
    ...

def save_global_defaults(defaults: dict) -> None:
    """Save entire global defaults dict."""
    ...
```

### Changes to `ThreadInfo`

Fields become Optional to distinguish "not set" vs "set to False":

```python
@dataclass
class ThreadInfo:
    auto_accept: bool | None = None  # None = inherit from global
    display_mode: str | None = None
    line_limit: int | None = None
    display_bullet: bool | None = None
    display_thinking_text: bool | None = None
    working_status: bool | None = None
    response_mode: str | None = None
    # ...
```

### Helper function

```python
def get_thread_setting(thread: ThreadInfo, key: str) -> Any:
    """Get effective setting: thread override or global default."""
    thread_value = getattr(thread, key, None)
    if thread_value is not None:
        return thread_value
    return get_global_defaults().get(key, HARDCODED_DEFAULTS[key])
```

### Migration

- Old threads with explicit values → preserved as overrides
- New threads → None everywhere, inherit global
- First launch after update: `global_defaults` doesn't exist → use hardcoded

## Files to Change

**New files:**
- `src/codogram/handlers/settings/reset.py` — `/reset_to_default` handler

**Changes:**

| File | What changes |
|------|-------------|
| `config.py` | `get_global_defaults()`, `set_global_default()`, `HARDCODED_DEFAULTS` |
| `core/session_manager.py` | `ThreadInfo` fields → Optional, `get_thread_setting()` helper |
| `handlers/dm.py` | Add `/settings` and `/reset_to_default` for DM |
| `services/menu.py` | Use `get_thread_setting()` |
| `telegram/keyboards/settings.py` | Variant without "claude" section for DM |
| `strings.py` | New strings for DM settings, confirmation, reset messages |
