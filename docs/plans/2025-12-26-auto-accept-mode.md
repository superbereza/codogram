# Auto-Accept Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically respond to Claude permission prompts without manual user interaction, with per-user per-project settings.

**Architecture:** Add `UserProjectSettingsManager` to config.py for settings storage. Modify `permission_poller.py` to check settings and auto-select safe options. Add `/auto_accept` command to bot.py.

**Tech Stack:** Python, aiogram, dataclasses, pytest

---

### Task 1: Create auto_accept module with detection functions

**Files:**
- Create: `src/codogram/auto_accept.py`
- Test: `tests/test_auto_accept.py`

**Step 1: Write the failing test for is_auto_acceptable**

```python
# tests/test_auto_accept.py
import pytest
from codogram.auto_accept import is_auto_acceptable, AUTO_ACCEPT_PHRASES

def test_is_auto_acceptable_yes_option():
    """First option with 'yes' triggers auto-accept."""
    options = ["1. Yes", "2. Yes, allow all edits", "3. Type here"]
    assert is_auto_acceptable(options) is True

def test_is_auto_acceptable_allow_option():
    """First option with 'allow' triggers auto-accept."""
    options = ["1. Allow once", "2. Allow for session", "3. No"]
    assert is_auto_acceptable(options) is True

def test_is_auto_acceptable_choice_question():
    """Choice questions (no trigger phrase) don't trigger."""
    options = ["1. src/main.py", "2. src/test.py", "3. Cancel"]
    assert is_auto_acceptable(options) is False

def test_is_auto_acceptable_empty():
    """Empty options don't trigger."""
    assert is_auto_acceptable([]) is False
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/codogram && source venv/bin/activate && pytest tests/test_auto_accept.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'codogram.auto_accept'"

**Step 3: Write minimal implementation**

```python
# src/codogram/auto_accept.py
"""Auto-accept mode for permission prompts."""
import re

# Configurable detection phrases
AUTO_ACCEPT_PHRASES = ["yes", "allow"]

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

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/codogram && source venv/bin/activate && pytest tests/test_auto_accept.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/personal-agent/agent-tools/codogram
git add src/codogram/auto_accept.py tests/test_auto_accept.py
git commit -m "feat(auto-accept): add is_auto_acceptable detection function"
```

---

### Task 2: Add select_option function with intelligent parsing

**Files:**
- Modify: `src/codogram/auto_accept.py`
- Modify: `tests/test_auto_accept.py`

**Step 1: Write the failing tests for select_option**

```python
# Add to tests/test_auto_accept.py
from codogram.auto_accept import select_option

def test_select_option_picks_yes():
    """Selects 'Yes' option, skipping session-wide."""
    options = ["1. Yes", "2. Yes, allow all edits", "3. Type here"]
    assert select_option(options) == "1"

def test_select_option_picks_allow_once():
    """Selects 'Allow once', skipping 'Allow for session'."""
    options = ["1. Allow once", "2. Allow for session", "3. No"]
    assert select_option(options) == "1"

def test_select_option_skips_session_wide():
    """Returns None when only session-wide option available."""
    options = ["1. Allow for session", "2. No"]
    assert select_option(options) is None

def test_select_option_no_match():
    """Returns None for choice questions."""
    options = ["1. src/main.py", "2. src/test.py", "3. Cancel"]
    assert select_option(options) is None

def test_select_option_empty():
    """Returns None for empty options."""
    assert select_option([]) is None

def test_select_option_finds_yes_in_middle():
    """Finds 'Yes' even if not first option (edge case)."""
    options = ["1. No", "2. Yes", "3. Cancel"]
    assert select_option(options) == "2"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/codogram && source venv/bin/activate && pytest tests/test_auto_accept.py::test_select_option_picks_yes -v`
Expected: FAIL with "ImportError: cannot import name 'select_option'"

**Step 3: Write minimal implementation**

```python
# Add to src/codogram/auto_accept.py

def select_option(options: list[str]) -> str | None:
    """Select option for auto-accept based on option content.

    Finds first option that matches AUTO_ACCEPT_PHRASES.
    Returns option number as string ("1", "2", etc.) or None if no match.

    Prefers single-action options ("Yes") over session-wide ("Allow for session").
    """
    if not options:
        return None

    for i, option in enumerate(options):
        option_lower = option.lower()

        # Skip session-wide permissions (too permissive)
        if "session" in option_lower or "all" in option_lower:
            continue

        # Check if option matches any accept phrase
        if any(phrase in option_lower for phrase in AUTO_ACCEPT_PHRASES):
            # Extract option number from text like "1. Yes" -> "1"
            match = re.match(r'^(\d+)\.', option.strip())
            if match:
                return match.group(1)
            return str(i + 1)

    return None
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/codogram && source venv/bin/activate && pytest tests/test_auto_accept.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
cd /home/superbereza/dev/personal-agent/agent-tools/codogram
git add src/codogram/auto_accept.py tests/test_auto_accept.py
git commit -m "feat(auto-accept): add select_option with intelligent parsing"
```

---

### Task 3: Create UserProjectSettings dataclass and manager

**Files:**
- Modify: `src/codogram/config.py`
- Create: `tests/test_user_project_settings.py`

**Step 1: Write the failing test**

```python
# tests/test_user_project_settings.py
import pytest
import tempfile
import json
from pathlib import Path

def test_user_project_settings_default_off():
    """Auto-accept is OFF by default for new user+project."""
    from codogram.config import UserProjectSettingsManager

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"projects": {}}, f)
        config_path = Path(f.name)

    try:
        manager = UserProjectSettingsManager(config_path)
        assert manager.is_auto_accept_enabled(12345, "test-project") is False
    finally:
        config_path.unlink()

def test_user_project_settings_set_and_get():
    """Can enable auto-accept for user+project."""
    from codogram.config import UserProjectSettingsManager

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"projects": {}}, f)
        config_path = Path(f.name)

    try:
        manager = UserProjectSettingsManager(config_path)
        manager.set_auto_accept(12345, "test-project", True)
        assert manager.is_auto_accept_enabled(12345, "test-project") is True
        assert manager.is_auto_accept_enabled(12345, "other-project") is False
        assert manager.is_auto_accept_enabled(99999, "test-project") is False
    finally:
        config_path.unlink()

def test_user_project_settings_persistence():
    """Settings persist after reload."""
    from codogram.config import UserProjectSettingsManager

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"projects": {}}, f)
        config_path = Path(f.name)

    try:
        # Set value
        manager1 = UserProjectSettingsManager(config_path)
        manager1.set_auto_accept(12345, "test-project", True)

        # Reload and check
        manager2 = UserProjectSettingsManager(config_path)
        assert manager2.is_auto_accept_enabled(12345, "test-project") is True
    finally:
        config_path.unlink()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/codogram && source venv/bin/activate && pytest tests/test_user_project_settings.py::test_user_project_settings_default_off -v`
Expected: FAIL with "ImportError: cannot import name 'UserProjectSettingsManager'"

**Step 3: Write minimal implementation**

```python
# Add to src/codogram/config.py (after save_config function)

from dataclasses import dataclass

@dataclass
class UserProjectSettings:
    """Settings for a user+project combination (extensible)."""
    user_id: int
    project_name: str
    auto_accept: bool = False

class UserProjectSettingsManager:
    """Manages per-user, per-project settings."""

    def __init__(self, config_path: Path | None = None):
        self._config_path = config_path or CONFIG_PATH
        self._config = self._load_config()
        # Nested dict: user_id -> project_name -> UserProjectSettings
        self._settings: dict[int, dict[str, UserProjectSettings]] = {}
        self._load()

    def _load_config(self) -> dict:
        """Load config from path."""
        if self._config_path.exists():
            return json.loads(self._config_path.read_text())
        return {"projects": {}}

    def _save_config(self) -> None:
        """Save config to path."""
        self._config_path.write_text(json.dumps(self._config, indent=2))

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
        self._save_config()

    def is_auto_accept_enabled(self, user_id: int, project_name: str) -> bool:
        """Check if auto-accept is enabled for user+project."""
        if user_id not in self._settings:
            return False
        if project_name not in self._settings[user_id]:
            return False
        return self._settings[user_id][project_name].auto_accept

    def set_auto_accept(self, user_id: int, project_name: str, enabled: bool) -> None:
        """Set auto-accept mode for user+project."""
        if user_id not in self._settings:
            self._settings[user_id] = {}
        if project_name not in self._settings[user_id]:
            self._settings[user_id][project_name] = UserProjectSettings(
                user_id=user_id,
                project_name=project_name
            )
        self._settings[user_id][project_name].auto_accept = enabled
        self._save()

# Global instance
user_project_settings = UserProjectSettingsManager()
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/codogram && source venv/bin/activate && pytest tests/test_user_project_settings.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/personal-agent/agent-tools/codogram
git add src/codogram/config.py tests/test_user_project_settings.py
git commit -m "feat(auto-accept): add UserProjectSettingsManager for per-user per-project settings"
```

---

### Task 4: Integrate auto-accept into permission_poller

**Files:**
- Modify: `src/codogram/permission_poller.py:90-130`

**Step 1: Read current code location**

The integration point is in `permission_poller_for_project()` at line 90-92, inside the `elif state == PollerState.DEBOUNCING:` block, after `if elapsed >= DEBOUNCE_TIME:`.

**Step 2: Modify permission_poller.py**

Add imports at top of file:
```python
from .auto_accept import is_auto_acceptable, select_option
from .config import user_project_settings, settings
```

Replace the block starting at line 92 (`# Send to Telegram`) with:

```python
                if elapsed >= DEBOUNCE_TIME:
                    # Get user_id for this chat (first admin for MVP)
                    admin_ids = settings.get_admin_ids()
                    user_id = list(admin_ids)[0] if admin_ids else None

                    # Check auto-accept mode (per-user, per-project)
                    auto_accept_enabled = (
                        user_id and
                        user_project_settings.is_auto_accept_enabled(user_id, project.project_name)
                    )

                    # Try auto-accept if enabled
                    if auto_accept_enabled:
                        selected = select_option(parsed.options)

                        if selected is not None:
                            # AUTO-ACCEPT PATH
                            body_preview = parsed.body[:100] if parsed.body else ""

                            # Find option text we're selecting
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

                            # Return to IDLE
                            state = PollerState.IDLE
                            last_options = None
                            last_body = None
                            continue

                        # select_option returned None → fall through to manual

                    # MANUAL PATH (existing code)
                    logger.debug(f"Poller DEBOUNCING→SHOWING: sending to Telegram")
```

**Step 3: Run existing tests to verify no regression**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/codogram && source venv/bin/activate && pytest tests/ -v`
Expected: PASS (all existing tests)

**Step 4: Commit**

```bash
cd /home/superbereza/dev/personal-agent/agent-tools/codogram
git add src/codogram/permission_poller.py
git commit -m "feat(auto-accept): integrate auto-accept into permission poller"
```

---

### Task 5: Add /auto_accept command to bot.py

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Find command handlers location**

Command handlers are defined with `@router.message(Command(...))` decorators. Add new command after existing commands.

**Step 2: Add the /auto_accept command handler**

```python
# Add import at top
from .config import user_project_settings

# Add command handler (after other command handlers)
@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message):
    """Toggle auto-accept mode for current user + current project."""
    if not is_admin(message.from_user.id):
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Find project for this chat
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("No project registered for this chat. Use /start first.")
        return

    args = message.text.split()[1:] if message.text else []

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

**Step 3: Run bot manually to verify command works**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/codogram && ./restart.sh`

Manual test:
1. Send `/auto_accept` in a registered project chat → should show status
2. Send `/auto_accept on` → should enable
3. Send `/auto_accept off` → should disable

**Step 4: Commit**

```bash
cd /home/superbereza/dev/personal-agent/agent-tools/codogram
git add src/codogram/bot.py
git commit -m "feat(auto-accept): add /auto_accept command"
```

---

### Task 6: Update /status command to show auto-accept state

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Find show_status function**

Search for `show_status` or the `/status` command handler.

**Step 2: Add auto-accept status line**

Add after session_id line:

```python
# Auto-accept status (per-user, per-project)
user_id = message.from_user.id
auto_enabled = user_project_settings.is_auto_accept_enabled(user_id, project.project_name)
auto_status = "⚡ ON" if auto_enabled else "OFF"
status_lines.append(f"Auto-accept: {auto_status}")
```

**Step 3: Run bot manually to verify**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/codogram && ./restart.sh`

Send `/status` in a registered project chat → should show auto-accept status line.

**Step 4: Commit**

```bash
cd /home/superbereza/dev/personal-agent/agent-tools/codogram
git add src/codogram/bot.py
git commit -m "feat(auto-accept): show auto-accept status in /status command"
```

---

### Task 7: Add /auto_accept to bot menu

**Files:**
- Modify: `src/codogram/main.py` (or wherever bot commands are registered)

**Step 1: Find bot commands registration**

Look for `set_my_commands` call.

**Step 2: Add auto_accept command to menu**

Add to the commands list:
```python
BotCommand(command="auto_accept", description="Toggle auto-accept mode"),
```

**Step 3: Restart bot and verify menu**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/codogram && ./restart.sh`

Check Telegram bot menu → should show /auto_accept command.

**Step 4: Commit**

```bash
cd /home/superbereza/dev/personal-agent/agent-tools/codogram
git add src/codogram/main.py
git commit -m "feat(auto-accept): add /auto_accept to bot menu"
```

---

### Task 8: Update ROADMAP.md

**Files:**
- Modify: `ROADMAP.md`

**Step 1: Move auto-accept from Backlog to Done**

Move the "Auto-accept mode" section from Backlog to Done section.

**Step 2: Commit**

```bash
cd /home/superbereza/dev/personal-agent/agent-tools/codogram
git add ROADMAP.md
git commit -m "docs: mark auto-accept mode as done in roadmap"
```

---

### Task 9: Manual integration test

**No code changes - manual testing only**

**Test checklist:**

1. [ ] Start bot: `./restart.sh`
2. [ ] In a registered project chat, send `/auto_accept` → should show OFF status
3. [ ] Send `/auto_accept on` → should enable
4. [ ] Send `/status` → should show "Auto-accept: ⚡ ON"
5. [ ] Trigger a permission prompt in Claude (e.g., ask Claude to create a file)
6. [ ] Verify: notification appears "🤖 Auto-accepted: ..." and no keyboard shown
7. [ ] Verify: log shows `auto_accept project=... user_id=... option="1. Yes"`
8. [ ] Send `/auto_accept off` → should disable
9. [ ] Trigger another permission prompt
10. [ ] Verify: keyboard shown (manual mode)
11. [ ] Restart bot: `./restart.sh`
12. [ ] Send `/auto_accept` → should still show previous state (persisted)

---

**Plan complete and saved to `docs/plans/2025-12-26-auto-accept-mode.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
