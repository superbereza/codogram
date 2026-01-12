# Session State Display Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `/shift_tab` command and enhance `/settings` to show Claude session state (approval mode, background tasks, context).

**Architecture:** Status bar parsing in `screen.py` (domain), business logic in `services/session_state.py`, thin handler in `handlers/shift_tab.py`. Enhance existing `handlers/settings.py`.

**Tech Stack:** Python, aiogram, regex for parsing

---

## Task 1: Add StatusBar dataclass to screen.py

**Files:**
- Modify: `src/codogram/screen.py:1-20`
- Test: `tests/test_screen.py` (create if not exists)

**Step 1: Write the failing test**

Create `tests/test_screen.py`:

```python
"""Tests for screen parsing."""
import pytest
from codogram.screen import StatusBar, parse_status_bar


class TestParseStatusBar:
    def test_parse_accept_edits_mode(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏵⏵ accept edits on (shift+tab to               Context left until
  cycle)                                         auto-compact: 45%
"""
        result = parse_status_bar(output)
        assert result.approval_mode == "accept edits"
        assert result.context_percent == 45

    def test_parse_plan_mode(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏸ plan mode on (shift+tab to cycle)
"""
        result = parse_status_bar(output)
        assert result.approval_mode == "plan mode"

    def test_parse_default_mode(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ? for shortcuts
"""
        result = parse_status_bar(output)
        assert result.approval_mode is None  # default mode

    def test_parse_background_tasks(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏵⏵ accept edits on · 2 background tasks
"""
        result = parse_status_bar(output)
        assert result.background_tasks == 2

    def test_parse_no_background_tasks(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏵⏵ accept edits on (shift+tab to cycle)
"""
        result = parse_status_bar(output)
        assert result.background_tasks == 0

    def test_parse_context_not_displayed(self):
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  1 background task
"""
        result = parse_status_bar(output)
        assert result.context_percent is None

    def test_parse_empty_output(self):
        """Empty output returns default values."""
        result = parse_status_bar("")
        assert result.approval_mode is None  # default mode
        assert result.background_tasks == 0
        assert result.context_percent is None

    def test_parse_only_background_tasks(self):
        """When only background tasks visible (during generation)."""
        output = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  2 background tasks
"""
        result = parse_status_bar(output)
        assert result.approval_mode is None  # default mode
        assert result.background_tasks == 2
        assert result.context_percent is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_screen.py -v`
Expected: FAIL with "cannot import name 'StatusBar'"

**Step 3: Add StatusBar dataclass**

Add to `src/codogram/screen.py` after line 16 (after `Idle` class):

```python
@dataclass
class StatusBar:
    """Claude CLI status bar state."""
    approval_mode: str | None  # "accept edits", "plan mode", None (default)
    background_tasks: int      # 0, 1, 2...
    context_percent: int | None  # 0-100 or None if not displayed
```

**Step 4: Add parse_status_bar function**

Add to `src/codogram/screen.py` at the end:

```python
def parse_status_bar(output: str) -> StatusBar:
    """Parse Claude CLI status bar from tmux capture-pane output.

    Status bar is below the input box (after last ──── separator).
    """
    lines = output.split("\n")

    # Find last separator (bottom of input box)
    last_sep_idx = -1
    for i, line in enumerate(lines):
        if "─" * 10 in line:
            last_sep_idx = i

    # Get lines after last separator (status bar area)
    status_lines = lines[last_sep_idx + 1:] if last_sep_idx >= 0 else []
    status_text = "\n".join(status_lines)

    # Parse approval mode by emoji detection
    approval_mode: str | None = None
    if "⏵⏵" in status_text:
        approval_mode = "accept edits"
    elif "⏸" in status_text:
        approval_mode = "plan mode"
    # else: default mode (None)

    # Parse background tasks
    background_tasks = 0
    bg_match = re.search(r'(\d+)\s+background\s+tasks?', status_text)
    if bg_match:
        background_tasks = int(bg_match.group(1))

    # Parse context percentage
    context_percent: int | None = None
    ctx_match = re.search(r'auto-compact:\s*(\d+)%', status_text)
    if ctx_match:
        context_percent = int(ctx_match.group(1))

    return StatusBar(
        approval_mode=approval_mode,
        background_tasks=background_tasks,
        context_percent=context_percent,
    )
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_screen.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/codogram/screen.py tests/test_screen.py
git commit -m "feat(screen): add StatusBar parsing for Claude CLI status bar"
```

---

## Task 2: Create SessionStateService

**Files:**
- Create: `src/codogram/services/session_state.py`
- Test: `tests/test_session_state_service.py`

**Step 1: Write the failing test**

Create `tests/test_session_state_service.py`:

```python
"""Tests for SessionStateService."""
import pytest
from unittest.mock import Mock, patch
from codogram.services.session_state import SessionStateService
from codogram.screen import StatusBar


class TestSessionStateService:
    def test_get_status_returns_status_bar(self):
        """Service should capture pane and parse status bar."""
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True
        mock_tmux.capture_pane.return_value = """
──────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────
  ⏵⏵ accept edits on · 1 background task
"""
        service = SessionStateService()
        result = service.get_status(mock_tmux)

        assert result.success is True
        assert result.status_bar.approval_mode == "accept edits"
        assert result.status_bar.background_tasks == 1

    def test_get_status_tmux_not_exists(self):
        """Service should return error if tmux doesn't exist."""
        mock_tmux = Mock()
        mock_tmux.exists.return_value = False

        service = SessionStateService()
        result = service.get_status(mock_tmux)

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_cycle_mode_sends_shift_tab(self):
        """Service should send S-Tab and return new mode."""
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True
        # First capture: accept edits, second capture: plan mode
        mock_tmux.capture_pane.side_effect = [
            "⏵⏵ accept edits on",  # before
            "⏸ plan mode on",       # after
        ]

        service = SessionStateService()
        result = service.cycle_approval_mode(mock_tmux)

        mock_tmux.send_key.assert_called_once_with("S-Tab")
        assert result.success is True
        assert result.new_mode == "plan mode"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_state_service.py -v`
Expected: FAIL with "No module named 'codogram.services.session_state'"

**Step 3: Create service file**

Create `src/codogram/services/session_state.py`:

```python
"""Session state service - status bar parsing and mode control."""
import asyncio
from dataclasses import dataclass

from ..screen import StatusBar, parse_status_bar
from ..tmux import TmuxSession


@dataclass
class StatusResult:
    """Result of get_status operation."""
    success: bool
    status_bar: StatusBar | None = None
    error: str | None = None


@dataclass
class CycleResult:
    """Result of cycle_approval_mode operation."""
    success: bool
    old_mode: str | None = None
    new_mode: str | None = None
    error: str | None = None


class SessionStateService:
    """Service for reading and controlling Claude session state."""

    def get_status(self, tmux: TmuxSession) -> StatusResult:
        """Get current session status from tmux.

        Args:
            tmux: TmuxSession instance

        Returns:
            StatusResult with parsed status bar or error
        """
        if not tmux.exists():
            return StatusResult(success=False, error="tmux session not found")

        output = tmux.capture_pane()
        status_bar = parse_status_bar(output)

        return StatusResult(success=True, status_bar=status_bar)

    def cycle_approval_mode(self, tmux: TmuxSession) -> CycleResult:
        """Send Shift+Tab to cycle approval mode.

        Args:
            tmux: TmuxSession instance

        Returns:
            CycleResult with old and new mode
        """
        if not tmux.exists():
            return CycleResult(success=False, error="tmux session not found")

        # Capture current mode
        output_before = tmux.capture_pane()
        old_status = parse_status_bar(output_before)
        old_mode = old_status.approval_mode

        # Send Shift+Tab
        try:
            tmux.send_key("S-Tab")
        except Exception as e:
            return CycleResult(success=False, error=f"Failed to send key: {e}")

        # Wait and capture new mode
        import time
        time.sleep(0.2)

        output_after = tmux.capture_pane()
        new_status = parse_status_bar(output_after)
        new_mode = new_status.approval_mode

        # Retry once if mode unchanged
        if new_mode == old_mode:
            time.sleep(0.2)
            output_after = tmux.capture_pane()
            new_status = parse_status_bar(output_after)
            new_mode = new_status.approval_mode

        return CycleResult(
            success=True,
            old_mode=old_mode,
            new_mode=new_mode,
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session_state_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/codogram/services/session_state.py tests/test_session_state_service.py
git commit -m "feat(services): add SessionStateService for status bar operations"
```

---

## Task 3: Create /shift_tab handler

**Files:**
- Create: `src/codogram/handlers/shift_tab.py`
- Modify: `src/codogram/handlers/__init__.py:4,18-26`

**Step 1: Create handler file**

Create `src/codogram/handlers/shift_tab.py`:

```python
"""Shift+Tab command handler."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from ..tmux import TmuxSession
from ..services.session_state import SessionStateService

router = Router(name="shift_tab")
service = SessionStateService()


def _get_tmux_for_context(chat_id: int, thread_id: int | None) -> TmuxSession | None:
    """Get TmuxSession for current chat/thread context."""
    project = project_manager.get_by_chat(chat_id)
    if not project:
        return None

    if thread_id and project.threads:
        thread = project.threads.get(thread_id)
        if thread:
            tmux_name = thread.get_tmux_session(project.project_name)
            return TmuxSession(tmux_name, thread.worktree_path or project.cwd)

    if project.tmux_session:
        return TmuxSession(project.tmux_session, project.cwd)

    return None


def _format_mode(mode: str | None) -> str:
    """Format approval mode for display."""
    if mode == "accept edits":
        return "⏵⏵ accept edits on"
    elif mode == "plan mode":
        return "⏸ plan mode on"
    else:
        return "default mode on"


@router.message(Command("shift_tab"))
async def cmd_shift_tab(message: Message, telegram_queue: TelegramQueue):
    """Send Shift+Tab to cycle Claude approval mode."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    tmux = _get_tmux_for_context(chat_id, thread_id)
    if not tmux:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    result = service.cycle_approval_mode(tmux)

    if not result.success:
        await telegram_queue.reply(message, result.error)
        return

    mode_text = _format_mode(result.new_mode)
    await telegram_queue.reply(message, mode_text)
```

**Step 2: Register router in __init__.py**

Edit `src/codogram/handlers/__init__.py`:

Change line 4:
```python
from . import permissions, start, threads, branches, sessions, settings, finish, common, messages, shift_tab
```

Add after line 23 (after settings.router):
```python
    dp.include_router(shift_tab.router)    # /shift_tab
```

**Step 3: Run bot and test manually**

Run: `./dev-run.sh`
Test: Send `/shift_tab` in Telegram
Expected: See mode change response

**Step 4: Commit**

```bash
git add src/codogram/handlers/shift_tab.py src/codogram/handlers/__init__.py
git commit -m "feat(handlers): add /shift_tab command to cycle approval mode"
```

---

## Task 4: Enhance /settings to show session state

**Files:**
- Modify: `src/codogram/handlers/settings.py:51-81`

**Step 1: Update cmd_settings function**

Replace the `cmd_settings` function in `src/codogram/handlers/settings.py`:

```python
@router.message(Command("settings"))
async def cmd_settings(message: Message, telegram_queue: TelegramQueue):
    """Show current settings including Claude session state."""
    from ..tmux import TmuxSession
    from ..services.session_state import SessionStateService

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    # Get auto-accept status
    if thread:
        auto_status = "⚡ ON" if thread.auto_accept else "OFF"
        context_name = thread.name
        tmux_name = thread.get_tmux_session(project.project_name)
        cwd = thread.worktree_path or project.cwd
    else:
        auto_status = "⚡ ON" if project.auto_accept else "OFF"
        context_name = project.project_name
        tmux_name = project.tmux_session
        cwd = project.cwd

    lines = [f"**Settings** (`{context_name}`)", ""]
    lines.append(f"Auto-accept: {auto_status}")

    # Get Claude session state from tmux
    if tmux_name:
        tmux = TmuxSession(tmux_name, cwd)
        service = SessionStateService()
        result = service.get_status(tmux)

        if not result.success:
            lines.append(f"Claude: {result.error}")
        else:
            sb = result.status_bar

            # Approval mode (None = default mode)
            if sb.approval_mode == "accept edits":
                mode_text = "⏵⏵ accept edits on"
            elif sb.approval_mode == "plan mode":
                mode_text = "⏸ plan mode on"
            else:
                mode_text = "default mode on"
            lines.append(f"{mode_text}, (/shift\\_tab to cycle)")

            # Background tasks
            if sb.background_tasks == 0:
                lines.append("no background tasks")
            elif sb.background_tasks == 1:
                lines.append("1 background task")
            else:
                lines.append(f"{sb.background_tasks} background tasks")

            # Context
            if sb.context_percent is not None:
                lines.append(f"context left until autocompact: {sb.context_percent}%")
            else:
                lines.append("context left until autocompact: not displayed")
    else:
        lines.append("Claude: not connected")

    await telegram_queue.reply(message, "\n".join(lines))
```

**Step 2: Run bot and test manually**

Run: `./dev-run.sh`
Test: Send `/settings` in Telegram
Expected: See settings with Claude session state

**Step 3: Commit**

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat(settings): show Claude session state in /settings"
```

---

## Task 5: Add /shift_tab to bot menu and /help

**Files:**
- Modify: `src/codogram/services/menu.py:12-24`
- Modify: `src/codogram/handlers/settings.py:27-46`

**Step 1: Add shift_tab to menu.py**

Edit `src/codogram/services/menu.py`, add to `_ALL_COMMANDS` list after line 20 (after "settings"):

```python
    ("shift_tab", "Cycle Claude approval mode", True),
```

**Step 2: Add shift_tab to /help command**

Edit `src/codogram/handlers/settings.py`, in `cmd_help` function, add after `/settings` line:

```python
/shift\\_tab — Cycle Claude approval mode
```

Full updated help text:
```python
    text = """*Everyday:*
/esc — Cancel current operation
/auto\\_accept — Toggle auto\\-accept mode

*Create:*
/thread — New topic in project directory
/branch — New isolated feature branch \\+ topic

*Complete:*
/clear — Clear context, start fresh
/finish — Merge branch, archive topic

*Settings:*
/start — Connect Claude or show status
/settings — View current settings
/shift\\_tab — Cycle Claude approval mode
/restart — Force restart Claude
/my\\_chat\\_id — Show chat and thread IDs

*Help:*
/help — This message"""
```

**Step 3: Run bot and verify**

Run: `./dev-run.sh`
Test: Check Telegram bot menu shows /shift_tab, check /help includes it
Expected: Command visible in menu and help

**Step 4: Commit**

```bash
git add src/codogram/services/menu.py src/codogram/handlers/settings.py
git commit -m "feat(menu): add /shift_tab to bot menu and help"
```

---

## Task 6: E2E Testing

**Files:**
- Reference: `docs/e2e/CLAUDE.md`

**Step 1: Test /shift_tab via Telegram MCP**

Ask user for test chat ID, then:

```python
# Send command
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/shift_tab")

# Read response
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=3)
```

Expected: Response shows new mode (e.g., "⏵⏵ accept edits on")

**Step 2: Test /settings via Telegram MCP**

```python
# Send command
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/settings")

# Read response
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=3)
```

Expected: Response shows settings with Claude status:
- Auto-accept status
- Approval mode with /shift_tab hint
- Background tasks count
- Context percentage

**Step 3: Test error cases**

Test `/shift_tab` in chat without registered project:
Expected: "No project. Use /start first."

**Step 4: Final commit**

```bash
git add -A
git commit -m "test: verify session state display E2E"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | StatusBar parsing | screen.py, test_screen.py |
| 2 | SessionStateService | services/session_state.py, test |
| 3 | /shift_tab handler | handlers/shift_tab.py, __init__.py |
| 4 | Enhance /settings | handlers/settings.py |
| 5 | Bot menu + help | services/menu.py, handlers/settings.py |
| 6 | E2E testing | manual via MCP |
