# Auto-Accept Mode Design

**Status:** Draft
**Created:** 2025-12-26
**Feature:** Automatic permission prompt acceptance for codogram

## Overview

Auto-accept mode automatically responds to Claude permission prompts without manual user interaction. This reduces friction for trusted workflows while maintaining audit trail and transparency.

Settings are **per-user, per-project** - each user can enable/disable auto-accept independently for each project they control.

## Core Behavior

### Trigger Criteria

Auto-accept activates only for prompts where the first option contains configurable phrases (default: "yes" or "allow"):

```python
# Configurable detection phrases
AUTO_ACCEPT_PHRASES = ["yes", "allow"]  # Easy to extend with new phrases

def is_auto_acceptable(options: list[str]) -> bool:
    """Check if prompt can be auto-accepted.

    Returns True if first option contains any AUTO_ACCEPT_PHRASES.
    Returns False for choice questions or other prompt types.
    """
    if not options:
        return False

    first_option = options[0].lower()
    return any(phrase in first_option for phrase in AUTO_ACCEPT_PHRASES)
```

**Real-world examples from Claude:**

✅ **Auto-accept:**
```
❯ 1. Yes
  2. Yes, allow all edits during this session (shift+tab)
  3. Type here to tell Claude what to do differently
```
First option: "Yes" → contains "yes" → auto-accept

✅ **Auto-accept:**
```
❯ 1. Allow once
  2. Allow for session
  3. No
```
First option: "Allow once" → contains "allow" → auto-accept

❌ **Manual response required:**
```
❯ 1. src/main.py
  2. src/test.py
  3. Cancel
```
First option: "src/main.py" → no trigger phrase → show in Telegram

### Option Selection

**Intelligently parse options to find the right one:**

```python
def select_option(options: list[str]) -> str | None:
    """Select option for auto-accept based on option content.

    Finds first option that matches AUTO_ACCEPT_PHRASES.
    Returns option number as string ("1", "2", etc.) or None if no match.

    Prefers single-action options ("Yes") over session-wide ("Allow for session").
    """
    if not options:
        return None

    # Parse option numbers and text
    # Options look like: "1. Yes", "2. Yes, allow all edits..."
    for i, option in enumerate(options):
        option_lower = option.lower()

        # Skip session-wide permissions (too permissive)
        if "session" in option_lower or "all" in option_lower:
            continue

        # Check if option matches any accept phrase
        if any(phrase in option_lower for phrase in AUTO_ACCEPT_PHRASES):
            # Extract option number from text like "1. Yes" -> "1"
            # Or return index+1 if no number found
            match = re.match(r'^(\d+)\.', option.strip())
            if match:
                return match.group(1)
            return str(i + 1)

    # Fallback: if no single-action option found, return None (manual mode)
    return None
```

**Examples:**

```python
# Standard Claude prompt
select_option(["1. Yes", "2. Yes, allow all edits...", "3. Type here..."])
# → "1" (picks "Yes", skips session-wide option)

# Allow prompt
select_option(["1. Allow once", "2. Allow for session", "3. No"])
# → "1" (picks "Allow once", skips session-wide)

# Choice question (no matching options)
select_option(["1. src/main.py", "2. src/test.py", "3. Cancel"])
# → None (no match, falls back to manual)

# Edge case: only session-wide available
select_option(["1. Allow for session", "2. No"])
# → None (refuse to auto-accept session-wide)
```

**Rationale:**
- Parse actual option content, don't assume position
- Prefer single-action ("Yes", "Allow once") over session-wide
- Return None when no safe option found → falls back to manual keyboard

## Implementation

### Data Model

#### Per-User, Per-Project Settings Structure

Settings are stored per-user, per-project to allow fine-grained control:

```python
# config.json structure:
{
    "user_project_settings": {
        "34185809": {  # user_id
            "codogram": {  # project_name
                "auto_accept": true
            },
            "personal-agent": {
                "auto_accept": false  # sensitive project, manual approval
            }
        },
        "98765432": {
            "codogram": {
                "auto_accept": true
            }
        }
    },
    "projects": {
        "codogram": {
            "chat_id": -1001234567890,
            "cwd": "/home/user/dev/codogram"
        }
    }
}
```

#### Config Management

Add user-project settings management to `config.py`:

```python
@dataclass
class UserProjectSettings:
    """Settings for a user+project combination (extensible)."""
    user_id: int
    project_name: str
    auto_accept: bool = False
    # Future settings fields:
    # notification_level: str = "normal"
    # custom_phrases: list[str] | None = None  # override global AUTO_ACCEPT_PHRASES

class UserProjectSettingsManager:
    """Manages per-user, per-project settings."""

    def __init__(self):
        self._config = load_config()
        # Nested dict: user_id -> project_name -> UserProjectSettings
        self._settings: dict[int, dict[str, UserProjectSettings]] = {}
        self._load()

    def _load(self) -> None:
        """Load user-project settings from config."""
        saved = self._config.get("user_project_settings", {})
        for user_id_str, projects in saved.items():
            user_id = int(user_id_str)
            self._settings[user_id] = {}
            for project_name, data in projects.items():
                self._settings[user_id][project_name] = UserProjectSettings(
                    user_id=user_id,
                    project_name=project_name,
                    auto_accept=data.get("auto_accept", False)
                )

    def _save(self) -> None:
        """Persist user-project settings to disk."""
        saved = {}
        for user_id, projects in self._settings.items():
            saved[str(user_id)] = {}
            for project_name, settings in projects.items():
                saved[str(user_id)][project_name] = {
                    "auto_accept": settings.auto_accept
                }
        self._config["user_project_settings"] = saved
        save_config(self._config)

    def get_or_create(self, user_id: int, project_name: str) -> UserProjectSettings:
        """Get existing settings or create new with defaults."""
        if user_id not in self._settings:
            self._settings[user_id] = {}
        if project_name not in self._settings[user_id]:
            self._settings[user_id][project_name] = UserProjectSettings(
                user_id=user_id,
                project_name=project_name
            )
        return self._settings[user_id][project_name]

    def set_auto_accept(self, user_id: int, project_name: str, enabled: bool) -> None:
        """Set auto-accept mode for user+project."""
        settings = self.get_or_create(user_id, project_name)
        settings.auto_accept = enabled
        self._save()

    def is_auto_accept_enabled(self, user_id: int, project_name: str) -> bool:
        """Check if auto-accept is enabled for user+project."""
        if user_id not in self._settings:
            return False
        if project_name not in self._settings[user_id]:
            return False
        return self._settings[user_id][project_name].auto_accept

# Global instance
user_project_settings = UserProjectSettingsManager()
```

### Permission Poller Integration

Modify `permission_poller_for_project()` in `permission_poller.py`:

```python
async def permission_poller_for_project(bot: Bot, project: ProjectState):
    """Background poller for permission prompts."""
    from .config import user_project_settings  # Import per-user, per-project settings

    logger.info(f"Permission poller started for project {project.project_name}")

    tmux = TmuxSession(project.tmux_session, project.cwd)
    chat_id = project.chat_id

    # Get admin user_id for this chat (first admin in ADMIN_IDS for MVP)
    # In multi-admin scenarios, would need to track which user controls this chat
    admin_ids = settings.get_admin_ids()
    user_id = list(admin_ids)[0] if admin_ids else None

    state = PollerState.IDLE
    debounce_start = 0.0
    last_options = None
    last_body = None
    content_msg_ids: list[int] = []
    kb_msg = None

    DEBOUNCE_TIME = 0.5
    POLL_INTERVAL = 0.5

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        try:
            screen = tmux.capture_pane()
            parsed = parse_screen(screen)
        except Exception as e:
            logger.warning(f"Permission poller: capture error: {e}")
            continue

        is_permission = isinstance(parsed, PermissionPrompt)

        # Debug: log if ❯ detected but no permission parsed
        if "❯" in screen and not is_permission:
            logger.debug(f"Poller: ❯ found but no permission! parsed={type(parsed).__name__}")

        # State machine transitions
        if state == PollerState.IDLE:
            if is_permission:
                logger.debug(f"Poller IDLE→DEBOUNCING: detected permission, options={parsed.options}")
                logger.debug(f"Poller: body={parsed.body[:100] if parsed.body else 'none'}...")
                state = PollerState.DEBOUNCING
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options

        elif state == PollerState.DEBOUNCING:
            if not is_permission:
                logger.debug("Poller DEBOUNCING→IDLE: permission disappeared")
                state = PollerState.IDLE
                last_options = None
            elif parsed.options != last_options:
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options
            else:
                elapsed = asyncio.get_event_loop().time() - debounce_start
                if elapsed >= DEBOUNCE_TIME:
                    # Check auto-accept mode (per-user, per-project)
                    auto_accept_enabled = (
                        user_id and
                        user_project_settings.is_auto_accept_enabled(user_id, project.project_name)
                    )

                    # Try auto-accept if enabled
                    if auto_accept_enabled:
                        selected = select_option(parsed.options)  # Returns str or None

                        if selected is not None:
                            # AUTO-ACCEPT PATH - found a safe option to select
                            body_preview = parsed.body[:100] if parsed.body else ""

                            # Find the option text we're selecting
                            option_idx = int(selected) - 1
                            option_text = (
                                parsed.options[option_idx]
                                if 0 <= option_idx < len(parsed.options)
                                else selected
                            )

                            logger.info(
                                "auto_accept",
                                extra={
                                    "project": project.project_name,
                                    "user_id": user_id,
                                    "auto": True,
                                    "option": option_text,
                                    "preview": body_preview,
                                }
                            )

                            # Send notification to Telegram
                            notification = f"🤖 Auto-accepted: {body_preview}..."
                            try:
                                await bot.send_message(chat_id, notification)
                            except Exception as e:
                                logger.warning(f"Failed to send auto-accept notification: {e}")

                            # Send key to tmux
                            tmux.send_key(selected)

                            # Return to IDLE (skip SHOWING state)
                            state = PollerState.IDLE
                            last_options = None
                            last_body = None
                            continue

                        # select_option returned None → no safe option found
                        # Fall through to MANUAL PATH below

                    # MANUAL PATH (existing code) - show keyboard to user
                    logger.debug(f"Poller DEBOUNCING→SHOWING: sending to Telegram")
                    logger.debug(f"Poller: body preview: {parsed.body[:200]}...")
                    try:
                        content_msg_ids = []

                        # Send body (description + content + question)
                        if parsed.body:
                            body_text = SEPARATOR_SOLID + "\n" + parsed.body
                            for chunk in chunk_message(body_text):
                                try:
                                    msg = await bot.send_message(
                                        chat_id, chunk, parse_mode="Markdown"
                                    )
                                except Exception:
                                    msg = await bot.send_message(chat_id, chunk)
                                content_msg_ids.append(msg.message_id)

                        # Send options as text (buttons have character limit)
                        options_text = "\n".join(parsed.options)
                        try:
                            opts_msg = await bot.send_message(chat_id, options_text)
                            content_msg_ids.append(opts_msg.message_id)
                        except Exception:
                            pass

                        kb = permission_keyboard(parsed.options, project.tmux_session)
                        kb_msg = await bot.send_message(
                            chat_id, "👆", reply_markup=kb
                        )
                        permission_messages[kb_msg.message_id] = content_msg_ids

                        state = PollerState.SHOWING
                        last_body = parsed.body
                        logger.debug(f"Poller SHOWING: sent {len(parsed.options)} options, kb_msg={kb_msg.message_id}")
                    except Exception as e:
                        logger.warning(f"Permission poller: send error: {e}")
                        state = PollerState.IDLE

        elif state == PollerState.SHOWING:
            # ... existing SHOWING state logic (unchanged) ...
            pass
```

### User Commands

Add `/auto_accept` command in `bot.py`:

```python
@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message):
    """Toggle auto-accept mode for current user + current project.

    Usage:
        /auto_accept on   - enable auto-accept for this project
        /auto_accept off  - disable auto-accept for this project
        /auto_accept      - show current status
    """
    if not is_admin(message.from_user.id):
        return

    from .config import user_project_settings

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Find project for this chat
    project = project_manager.get_by_chat_id(chat_id)
    if not project:
        await message.answer("No project registered for this chat. Use /start first.")
        return

    args = message.text.split()[1:]  # Skip /auto_accept

    if not args:
        # Show status
        enabled = user_project_settings.is_auto_accept_enabled(user_id, project.project_name)
        status = "ON ⚡" if enabled else "OFF"
        await message.answer(
            f"Auto-accept mode: **{status}**\n\n"
            f"Project: `{project.project_name}`\n\n"
            f"Use `/auto_accept on` or `/auto_accept off` to toggle.",
            parse_mode="Markdown"
        )
        return

    mode = args[0].lower()
    if mode == "on":
        user_project_settings.set_auto_accept(user_id, project.project_name, True)
        await message.answer(
            f"⚡ Auto-accept mode **ENABLED** for `{project.project_name}`",
            parse_mode="Markdown"
        )
    elif mode == "off":
        user_project_settings.set_auto_accept(user_id, project.project_name, False)
        await message.answer(
            f"Auto-accept mode **DISABLED** for `{project.project_name}`",
            parse_mode="Markdown"
        )
    else:
        await message.answer("Usage: `/auto_accept on|off`", parse_mode="Markdown")
```

Update `/status` command to show auto-accept state:

```python
async def show_status(message: Message, project: ProjectState):
    """Show status of active Claude session."""
    from .config import user_project_settings

    status_lines = [
        f"**Claude активен**",
        f"",
        f"Проект: `{project.project_name}`",
        f"Путь: `{project.cwd}`",
        f"Tmux: `{project.tmux_session}`",
    ]

    if project.session_id:
        status_lines.append(f"Session: `{project.session_id[:8]}...`")

    # Auto-accept status (per-user, per-project)
    user_id = message.from_user.id
    auto_enabled = user_project_settings.is_auto_accept_enabled(user_id, project.project_name)
    auto_status = "⚡ ON" if auto_enabled else "OFF"
    status_lines.append(f"Auto-accept: {auto_status}")

    status_lines.extend([
        "",
        f"Подключиться: `tmux attach -t {project.tmux_session}`",
    ])

    await message.answer("\n".join(status_lines), parse_mode="Markdown")
```

## Logging

Auto-accepted actions logged at INFO level:

```python
logger.info(
    "auto_accept",
    extra={
        "project": "codogram",
        "user_id": 34185809,
        "auto": True,
        "option": "1. Yes",
        "preview": "Run bash command: git status...",
    }
)
```

**Log output example:**
```
2025-12-26 14:23:45 INFO auto_accept project=codogram user_id=34185809 auto=true option="1. Yes" preview="Run bash command: git status..."
```

## Safety & Edge Cases

### Default State
- Auto-accept is **OFF by default** for new user+project combinations
- Requires explicit opt-in via `/auto_accept on` in each project chat

### Per-User, Per-Project Settings
- Auto-accept setting is independent for each user+project combination
- User can enable auto-accept for trusted projects, keep manual for sensitive ones
- Different admins can have different settings for the same project

### Non-Matching Prompts
- Prompts that don't match `is_auto_acceptable()` criteria:
  - Show normally in Telegram with keyboard
  - Require manual user response
  - Auto-accept mode remains ON (applies to next matching prompt)

### Manual Button Clicks
- If user clicks a permission button manually:
  - Standard callback handler processes the click (existing code)
  - No special logic needed - race condition between auto-accept timer and manual click
  - Whichever arrives first at tmux wins (tmux processes key sequentially)

### Rapid Prompts
- Multiple prompts in quick succession:
  - Each prompt debounced independently (0.5s)
  - Auto-accept applies to each matching prompt sequentially
  - No loop protection in MVP (v2 feature)

### Persistence
- User settings persist in config.json
- Survives bot restarts
- Auto-loaded on startup

## User Experience

### Enabling Auto-Accept

```
User: /auto_accept on
Bot:  ⚡ Auto-accept mode ENABLED for `codogram`
```

### Auto-Accept in Action

```
Bot: 🤖 Auto-accepted: Run bash command: git status...
```

### Status Check

```
User: /status
Bot:  Claude активен

      Проект: codogram
      Путь: /home/user/dev/codogram
      Tmux: claude-codogram
      Session: a3f2c1b8...
      Auto-accept: ⚡ ON

      Подключиться: tmux attach -t claude-codogram
```

### Disabling Auto-Accept

```
User: /auto_accept off
Bot:  Auto-accept mode DISABLED for `codogram`
```

### Different Settings Per Project

```
# In codogram chat:
User: /auto_accept on
Bot:  ⚡ Auto-accept mode ENABLED for `codogram`

# In personal-agent chat (different project):
User: /auto_accept
Bot:  Auto-accept mode: OFF
      Project: personal-agent
```

## Future Enhancements (v2)

**Not in MVP scope:**

1. **Keyword blocklist** - block auto-accept for dangerous operations (rm -rf, drop table)
2. **Custom phrases** - per-user, per-project configurable `AUTO_ACCEPT_PHRASES`
3. **Tool-specific filters** - whitelist/blacklist specific tools
4. **Loop detection** - pause auto-accept if too many prompts in short time
5. **Structured parsing** - extract tool_name and args from prompt body
6. **JSON logging** - machine-readable audit trail
7. **Time expiry** - auto-disable after N hours
8. **Notification levels** - minimal/normal/verbose (per-user, per-project preference)
9. **Smart option selection** - ML-based learning of user preferences

## Extensibility: Future Settings

The `UserProjectSettings` dataclass is designed to be extensible. Future settings can be added without breaking existing code:

```python
@dataclass
class UserProjectSettings:
    """Settings for a user+project combination (extensible)."""
    user_id: int
    project_name: str
    auto_accept: bool = False

    # Future settings (examples):
    # notification_level: str = "normal"  # minimal/normal/verbose
    # custom_phrases: list[str] | None = None  # override global AUTO_ACCEPT_PHRASES
    # compact_mode: bool = False  # compact message formatting
```

All future fields automatically persist via `_save()` method without code changes.

## Testing Strategy

### Unit Tests

1. `test_is_auto_acceptable()` - verify trigger criteria with configurable phrases
2. `test_select_option()` - verify intelligent option parsing:
   - Returns "1" for "Yes" option
   - Returns None for choice questions (no matching phrase)
   - Skips session-wide options ("allow all", "for session")
3. `test_user_project_settings_persistence()` - verify auto_accept saves/loads per user+project
4. `test_extensible_settings()` - verify unknown fields don't break loading

### Integration Tests

1. Enable auto-accept → verify prompt auto-handled
2. Non-matching prompt → verify shows in Telegram (manual fallback)
3. `select_option` returns None → verify falls back to manual keyboard
4. Bot restart → verify user+project settings restored
5. `/status` command → verify auto-accept status displayed for current project
6. Multi-user scenario → verify per-user isolation
7. Multi-project scenario → verify per-project isolation (same user, different settings)

### Manual Testing Checklist

- [ ] `/auto_accept on` enables mode for current user+project
- [ ] `/auto_accept off` disables mode for current user+project
- [ ] `/auto_accept` shows current status with project name
- [ ] Auto-accept sends notification to Telegram
- [ ] Auto-accept logged at INFO level with user_id and project
- [ ] Non-yes/allow prompts show keyboard (manual fallback)
- [ ] Session-wide options skipped (only single-action accepted)
- [ ] `/status` shows user's auto-accept state for current project
- [ ] User+project settings persist after bot restart
- [ ] Different projects have independent auto-accept settings
- [ ] Different users have independent auto-accept settings for same project

## Implementation Checklist

- [ ] Create `UserProjectSettings` dataclass with extensible structure
- [ ] Implement `UserProjectSettingsManager` class
- [ ] Add `user_project_settings` section to config.json structure
- [ ] Implement `_load()` and `_save()` methods for nested user→project structure
- [ ] Define `AUTO_ACCEPT_PHRASES` constant (configurable array)
- [ ] Implement `is_auto_acceptable()` function
- [ ] Implement `select_option()` function with intelligent parsing:
  - Parse option content, not just position
  - Skip session-wide permissions ("all", "session")
  - Return None when no safe option found
- [ ] Modify `permission_poller_for_project()` to check user+project auto-accept setting
- [ ] Handle `select_option()` returning None → fall back to manual keyboard
- [ ] Add logging for auto-accepted actions (include user_id and project)
- [ ] Add Telegram notification for auto-accepts
- [ ] Implement `/auto_accept` command (per-user, per-project)
- [ ] Update `/status` command to show auto-accept state for current project
- [ ] Write unit tests (including select_option edge cases)
- [ ] Write integration tests
- [ ] Update ROADMAP.md (move to Done after implementation)

---

**Design complete.** Ready for implementation.
