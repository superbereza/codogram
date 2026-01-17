# Verbose Toggle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add short/long display mode toggle for tool calls, permissions, and auto-accept messages.

**Architecture:** Per-thread `verbose` boolean (default: False = short mode). Short mode truncates body to 5 lines. Settings command shows status with inline keyboard for toggling.

**Tech Stack:** Python, aiogram, pytest

---

## Task 1: Add `verbose` field to data model

**Files:**
- Modify: `src/codogram/session_manager.py:87-146` (ThreadInfo and ProjectState)
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

Add to `tests/test_session_manager.py`:

```python
def test_thread_info_verbose_default():
    """ThreadInfo.verbose defaults to False (short mode)."""
    thread = ThreadInfo(thread_id=None, name="main")
    assert thread.verbose is False


def test_project_state_verbose_default():
    """ProjectState.verbose defaults to False (short mode)."""
    project = ProjectState(project_name="test")
    assert project.verbose is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py::test_thread_info_verbose_default tests/test_session_manager.py::test_project_state_verbose_default -v`
Expected: FAIL with AttributeError

**Step 3: Add verbose field to ThreadInfo**

In `src/codogram/session_manager.py`, add after line 115 (`auto_accept: bool = False`):

```python
    # Verbose output mode (show full body):
    verbose: bool = False              # False = short (5 lines), True = full
```

**Step 4: Add verbose field to ProjectState**

In `src/codogram/session_manager.py`, add after line 159 (`auto_accept: bool = False`):

```python
    # Verbose output mode (project-wide default):
    verbose: bool = False
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py::test_thread_info_verbose_default tests/test_session_manager.py::test_project_state_verbose_default -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/codogram/session_manager.py tests/test_session_manager.py
git commit -m "feat: add verbose field to ThreadInfo and ProjectState"
```

---

## Task 2: Persist verbose field to config

**Files:**
- Modify: `src/codogram/session_manager.py:241-281` (_save method)
- Modify: `src/codogram/session_manager.py:192-239` (_load_projects method)
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

Add to `tests/test_session_manager.py`:

```python
def test_verbose_persisted_in_config(tmp_path, monkeypatch):
    """verbose field should be saved and loaded from config."""
    import json
    from codogram.session_manager import ProjectManager
    from codogram import config

    # Use temp config
    test_config = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", test_config)
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)

    # Create manager and set verbose
    manager = ProjectManager()
    project = manager.get_or_create("test-project")
    project.chat_id = 123
    project.cwd = "/tmp/test"
    thread = project.get_or_create_thread(None, "main")
    thread.verbose = True
    project.verbose = True
    manager._save()

    # Reload and check
    saved = json.loads(test_config.read_text())
    assert saved["projects"]["test-project"]["verbose"] is True
    assert saved["projects"]["test-project"]["threads"]["null"]["verbose"] is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py::test_verbose_persisted_in_config -v`
Expected: FAIL (key not in saved data)

**Step 3: Update _save to persist verbose**

In `src/codogram/session_manager.py` `_save` method, after line 247 (project_data creation):

```python
            project_data = {"chat_id": p.chat_id, "cwd": p.cwd, "auto_accept": p.auto_accept, "verbose": p.verbose}
```

And in thread_data dict (around line 268), add after auto_accept:

```python
                    if t.verbose:
                        thread_data["verbose"] = t.verbose
```

**Step 4: Update _load_projects to load verbose**

In `src/codogram/session_manager.py` `_load_projects` method, after line 204:

```python
                project.verbose = data.get("verbose", False)
```

And in thread loading (around line 224), add:

```python
                        verbose=thread_data.get("verbose", False),
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py::test_verbose_persisted_in_config -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/codogram/session_manager.py tests/test_session_manager.py
git commit -m "feat: persist verbose field to config"
```

---

## Task 3: Add truncate_body helper

**Files:**
- Create: `src/codogram/utils/truncate.py`
- Test: `tests/test_truncate.py`

**Step 1: Write the failing test**

Create `tests/test_truncate.py`:

```python
import pytest
from codogram.utils.truncate import truncate_body

MAX_LINES = 5


def test_truncate_body_short_text():
    """Text under limit is returned as-is."""
    text = "line1\nline2\nline3"
    result = truncate_body(text, verbose=False)
    assert result == text
    assert "[truncated]" not in result


def test_truncate_body_exact_limit():
    """Text at exactly 5 lines is returned as-is."""
    text = "\n".join([f"line{i}" for i in range(5)])
    result = truncate_body(text, verbose=False)
    assert result == text
    assert "[truncated]" not in result


def test_truncate_body_over_limit():
    """Text over 5 lines is truncated with indicator."""
    text = "\n".join([f"line{i}" for i in range(10)])
    result = truncate_body(text, verbose=False)
    lines = result.split("\n")
    assert len(lines) == 6  # 5 lines + "[truncated]"
    assert lines[-1] == "[truncated]"


def test_truncate_body_verbose_mode():
    """In verbose mode, text is returned as-is regardless of length."""
    text = "\n".join([f"line{i}" for i in range(20)])
    result = truncate_body(text, verbose=True)
    assert result == text
    assert "[truncated]" not in result


def test_truncate_body_none():
    """None input returns None."""
    assert truncate_body(None, verbose=False) is None


def test_truncate_body_empty():
    """Empty string returns empty string."""
    assert truncate_body("", verbose=False) == ""
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_truncate.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create utils directory and truncate module**

First, create the utils directory:

```bash
mkdir -p src/codogram/utils
```

Create `src/codogram/utils/__init__.py`:

```python
"""Utility functions."""
from .truncate import truncate_body

__all__ = ["truncate_body"]
```

Create `src/codogram/utils/truncate.py`:

```python
"""Body truncation for short/long display mode."""

MAX_LINES = 5


def truncate_body(text: str | None, verbose: bool) -> str | None:
    """Truncate body text based on verbose setting.

    Args:
        text: Body text to truncate (or None)
        verbose: If True, return full text. If False, truncate to MAX_LINES.

    Returns:
        Truncated text with "..." suffix, or full text if verbose=True.
    """
    if text is None:
        return None

    if verbose:
        return text

    lines = text.split("\n")
    if len(lines) <= MAX_LINES:
        return text

    return "\n".join(lines[:MAX_LINES]) + "\n[truncated]"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_truncate.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/utils/ tests/test_truncate.py
git commit -m "feat: add truncate_body helper for short/long mode"
```

---

## Task 4: Apply truncation to permission_poller

**Files:**
- Modify: `src/codogram/permission_poller.py:186-196` (DEBOUNCING->SHOWING)
- Test: `tests/test_permission_poller.py`

**Step 1: Write the failing test**

Add to `tests/test_permission_poller.py`:

```python
from codogram.utils.truncate import truncate_body


def test_permission_body_truncated_in_short_mode():
    """Permission body should be truncated when verbose=False."""
    long_body = "\n".join([f"line{i}" for i in range(10)])
    result = truncate_body(long_body, verbose=False)
    assert result.count("\n") == 5  # 5 lines + "[truncated]"
    assert result.endswith("[truncated]")


def test_permission_body_full_in_verbose_mode():
    """Permission body should be full when verbose=True."""
    long_body = "\n".join([f"line{i}" for i in range(10)])
    result = truncate_body(long_body, verbose=True)
    assert result == long_body
```

**Step 2: Run test to verify it passes (truncate already works)**

Run: `pytest tests/test_permission_poller.py::test_permission_body_truncated_in_short_mode tests/test_permission_poller.py::test_permission_body_full_in_verbose_mode -v`
Expected: PASS (helper already exists)

**Step 3: Apply truncation in permission_poller**

In `src/codogram/permission_poller.py`, add import at top:

```python
from .utils.truncate import truncate_body
```

In the DEBOUNCING->SHOWING transition (around line 191), before building messages:

```python
                    # Get verbose setting from context
                    verbose_enabled = thread.verbose if thread else project.verbose
                    display_body = truncate_body(parsed.body, verbose=verbose_enabled)
```

Then replace `parsed.body` with `display_body` in the message building (line 195):

```python
                        if display_body:
                            body_text = SEPARATOR_SOLID + "\n" + display_body
```

Do the same for the SHOWING resend block (around line 267).

**Step 4: Run full permission_poller tests**

Run: `pytest tests/test_permission_poller.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/permission_poller.py tests/test_permission_poller.py
git commit -m "feat: apply truncation to permission prompts"
```

---

## Task 5: Apply truncation to auto_accept

**Files:**
- Modify: `src/codogram/auto_accept.py:43-77`
- Test: `tests/test_auto_accept.py`

**Step 1: Write the failing test**

Add to `tests/test_auto_accept.py`:

```python
@pytest.mark.asyncio
async def test_try_auto_accept_truncates_in_short_mode():
    """Body should be truncated when verbose=False."""
    tmux = MagicMock()
    queue = AsyncMock()

    long_body = "\n".join([f"line{i}" for i in range(10)])

    result = await try_auto_accept(
        options=["1. Yes"],
        body=long_body,
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=None,
        context_name="test",
        verbose=False,
    )

    assert result is True
    call_args = queue.enqueue_nowait.call_args[0][0]
    sent_text = call_args.messages[0]["text"]
    # Should be truncated
    assert sent_text.count("\n") <= 6  # "🤖 Auto: " + 5 lines + "..."
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_auto_accept.py::test_try_auto_accept_truncates_in_short_mode -v`
Expected: FAIL (unexpected keyword argument 'verbose')

**Step 3: Add verbose parameter to try_auto_accept**

In `src/codogram/auto_accept.py`, add import:

```python
from .utils.truncate import truncate_body
```

Update function signature (line 43):

```python
async def try_auto_accept(
    options: list[str],
    body: str | None,
    tmux: TmuxSession,
    telegram_queue: "TelegramQueue",
    chat_id: int,
    thread_id: int | None,
    context_name: str,
    prompt_type: PromptType = PromptType.REGULAR,
    verbose: bool = False,
) -> bool:
```

Update body_text assignment (around line 66):

```python
    body_text = truncate_body(body, verbose=verbose) if body else "[no details]"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_auto_accept.py -v`
Expected: PASS

**Step 5: Update permission_poller to pass verbose to try_auto_accept**

In `src/codogram/permission_poller.py`, update the try_auto_accept call (around line 180):

```python
                        if await try_auto_accept(
                            parsed.options, parsed.body, tmux,
                            telegram_queue, project.chat_id, thread_id, context_name,
                            prompt_type=parsed.prompt_type,
                            verbose=verbose_enabled,
                        ):
```

**Step 6: Run all tests**

Run: `pytest tests/test_auto_accept.py tests/test_permission_poller.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add src/codogram/auto_accept.py src/codogram/permission_poller.py tests/test_auto_accept.py
git commit -m "feat: apply truncation to auto-accept messages"
```

---

## Task 6: Apply truncation to watcher tool calls

**Files:**
- Modify: `src/codogram/watcher.py:77-110` (format_tool_use)
- Test: `tests/test_watcher.py`

**Step 1: Write the failing test**

Add to `tests/test_watcher.py`:

```python
from codogram.watcher import format_tool_use


def test_format_tool_use_bash_truncates_in_short_mode():
    """Bash command should be truncated when verbose=False."""
    long_cmd = "\n".join([f"echo line{i}" for i in range(10)])
    result = format_tool_use("Bash", {"command": long_cmd}, verbose=False)
    # Should truncate the command to 5 lines + [truncated]
    assert "[truncated]" in result
    # Original 10 lines should NOT be fully present
    assert "echo line9" not in result


def test_format_tool_use_bash_full_in_verbose_mode():
    """Bash command should be full when verbose=True."""
    long_cmd = "\n".join([f"echo line{i}" for i in range(10)])
    result = format_tool_use("Bash", {"command": long_cmd}, verbose=True)
    # All 10 lines should be present
    assert "echo line9" in result
    assert "[truncated]" not in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_watcher.py::test_format_tool_use_bash_truncates_in_short_mode -v`
Expected: FAIL (unexpected keyword argument)

**Step 3: Add verbose parameter to format_tool_use**

In `src/codogram/watcher.py`, add import:

```python
from .utils.truncate import truncate_body
```

Update function signature (line 77):

```python
def format_tool_use(tool_name: str, tool_input: dict | None, verbose: bool = False) -> str:
```

For Bash command, apply truncation (around line 83):

```python
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")[:500]
        desc = tool_input.get("description", "")
        cmd_display = truncate_body(cmd, verbose=verbose) or cmd
        if desc:
            return f"● **Bash**: {desc}\n`{cmd_display}`"
        return f"● **Bash**\n`{cmd_display}`"
```

For default case (line 109):

```python
    else:
        preview = str(tool_input)[:200]
        preview = truncate_body(preview, verbose=verbose) or preview
        return f"● **{tool_name}**\n`{preview}`"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_watcher.py -v`
Expected: PASS

**Step 5: Update _entry_to_messages to get verbose setting**

The watcher needs access to verbose setting. This requires passing it through. Update `_watch_with_queue` to receive verbose getter.

In `src/codogram/watcher.py`, update `_entry_to_messages` signature:

```python
def _entry_to_messages(entry: ParsedEntry, verbose: bool = False) -> list[dict]:
```

And pass verbose to format_tool_use:

```python
    elif entry.content_type == ContentType.TOOL_USE:
        text = format_tool_use(entry.tool_name, entry.tool_input, verbose=verbose)
```

**Step 6: Commit**

```bash
git add src/codogram/watcher.py tests/test_watcher.py
git commit -m "feat: apply truncation to tool call display"
```

---

## Task 7: Create settings keyboard builder

**Files:**
- Create: `src/codogram/keyboards/settings.py`
- Modify: `src/codogram/keyboards/__init__.py`
- Test: `tests/unit/keyboards/test_settings.py`

**Step 1: Write the failing test**

Create `tests/unit/keyboards/test_settings.py`:

```python
import pytest
from codogram.keyboards.settings import settings_keyboard


def test_settings_keyboard_structure():
    """Settings keyboard has 3 vertical buttons."""
    kb = settings_keyboard("claude-test")

    # 3 rows, 1 button each
    assert len(kb.inline_keyboard) == 3
    assert len(kb.inline_keyboard[0]) == 1
    assert len(kb.inline_keyboard[1]) == 1
    assert len(kb.inline_keyboard[2]) == 1


def test_settings_keyboard_button_labels():
    """Buttons show command names."""
    kb = settings_keyboard("claude-test")

    assert kb.inline_keyboard[0][0].text == "/auto_accept"
    assert kb.inline_keyboard[1][0].text == "/verbose"
    assert kb.inline_keyboard[2][0].text == "/shift_tab"


def test_settings_keyboard_callback_data():
    """Callback data includes tmux session name."""
    kb = settings_keyboard("claude-test")

    assert kb.inline_keyboard[0][0].callback_data == "settings:auto_accept:claude-test"
    assert kb.inline_keyboard[1][0].callback_data == "settings:verbose:claude-test"
    assert kb.inline_keyboard[2][0].callback_data == "settings:mode:claude-test"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/keyboards/test_settings.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create settings keyboard**

Create `src/codogram/keyboards/settings.py`:

```python
"""Settings inline keyboard."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def settings_keyboard(tmux_session: str) -> InlineKeyboardMarkup:
    """Build settings keyboard with toggle buttons.

    Args:
        tmux_session: Tmux session name for callback routing

    Returns:
        InlineKeyboardMarkup with vertical buttons:
        - /auto_accept
        - /verbose
        - /shift_tab
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="/auto_accept",
            callback_data=f"settings:auto_accept:{tmux_session}"
        )],
        [InlineKeyboardButton(
            text="/verbose",
            callback_data=f"settings:verbose:{tmux_session}"
        )],
        [InlineKeyboardButton(
            text="/shift_tab",
            callback_data=f"settings:mode:{tmux_session}"
        )],
    ])
```

**Step 4: Update keyboards __init__.py**

```python
"""Keyboard builders for Telegram bot."""
from .permissions import permission_keyboard
from .settings import settings_keyboard

__all__ = ["permission_keyboard", "settings_keyboard"]
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/unit/keyboards/test_settings.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/codogram/keyboards/ tests/unit/keyboards/test_settings.py
git commit -m "feat: add settings keyboard builder"
```

---

## Task 8: Update /settings command output

**Files:**
- Modify: `src/codogram/handlers/settings.py:54-123`
- Test: E2E via Telegram MCP

**Step 1: Add _build_settings_text helper**

Add helper function to `src/codogram/handlers/settings.py` (before cmd_settings):

```python
def _build_settings_text(project, thread, tmux_name: str) -> str:
    """Build settings message text. Used by cmd_settings and callback handler."""
    from ..tmux import TmuxSession
    from ..services.session_state import SessionStateService

    # Get settings from context
    if thread:
        auto_accept = thread.auto_accept
        verbose = thread.verbose
        context_name = thread.name
        cwd = thread.worktree_path or project.cwd
    else:
        auto_accept = project.auto_accept
        verbose = project.verbose
        context_name = project.project_name
        cwd = project.cwd

    # Format toggle indicators
    auto_status = "● on" if auto_accept else "○ off"
    verbose_status = "● on" if verbose else "○ off"

    lines = [f"**{context_name}**", ""]
    lines.append("chat")
    lines.append(f"• auto-accept: {auto_status}")
    lines.append(f"• verbose: {verbose_status}")
    lines.append("")
    lines.append("claude")

    # Get Claude session state from tmux
    if tmux_name:
        tmux = TmuxSession(tmux_name, cwd)
        service = SessionStateService()
        result = service.get_status(tmux)

        if not result.success:
            lines.append(f"• mode: {result.error}")
            lines.append("• background tasks: ?")
            lines.append("• context: ?")
        else:
            sb = result.status_bar

            # Approval mode
            if sb.approval_mode == "accept edits":
                mode_text = "accept edits"
            elif sb.approval_mode == "plan mode":
                mode_text = "plan mode"
            else:
                mode_text = "default"
            lines.append(f"• mode: {mode_text}")
            lines.append(f"• background tasks: {sb.background_tasks}")

            if sb.context_percent is not None:
                lines.append(f"• context: {sb.context_percent}%")
            else:
                lines.append("• context: not displayed")
    else:
        lines.append("• mode: not connected")
        lines.append("• background tasks: ?")
        lines.append("• context: ?")

    return "\n".join(lines)
```

**Step 2: Update cmd_settings to use helper**

```python
@router.message(Command("settings"))
async def cmd_settings(message: Message, telegram_queue: TelegramQueue):
    """Show current settings including Claude session state."""
    from ..keyboards import settings_keyboard

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    # Get tmux name for keyboard
    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
    else:
        tmux_name = project.tmux_session or f"claude-{project.project_name}"

    text = _build_settings_text(project, thread, tmux_name)
    kb = settings_keyboard(tmux_name)
    await telegram_queue.reply(message, text, reply_markup=kb)
```

**Step 3: Test via Telegram MCP**

Send `/settings` command and verify output format matches design.

**Step 4: Commit**

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat: update /settings output with new format and keyboard"
```

---

## Task 9: Add /verbose command

**Files:**
- Modify: `src/codogram/handlers/settings.py`
- Test: E2E via Telegram MCP

**Step 1: Add /verbose handler**

Add to `src/codogram/handlers/settings.py`:

```python
@router.message(Command("verbose"))
async def cmd_verbose(message: Message, telegram_queue: TelegramQueue):
    """Toggle verbose output mode."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    # Toggle verbose
    if thread:
        thread.verbose = not thread.verbose
        status = "● on" if thread.verbose else "○ off"
    else:
        project.verbose = not project.verbose
        status = "● on" if project.verbose else "○ off"

    project_manager._save()
    await telegram_queue.reply(message, f"Verbose output: {status}")
```

**Step 2: Test via Telegram MCP**

Send `/verbose` and verify toggle works.

**Step 3: Commit**

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat: add /verbose toggle command"
```

---

## Task 10: Update /auto_accept response format

**Files:**
- Modify: `src/codogram/handlers/settings.py:126-165`

**Step 1: Update response format**

Update `cmd_auto_accept` to use circle indicators:

```python
@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message, telegram_queue: TelegramQueue):
    """Toggle auto-accept or reset all."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    args = (message.text or "").split()[1:]

    # /auto_accept reset all - reset all to off
    if len(args) >= 2 and args[0].lower() == "reset" and args[1].lower() == "all":
        project.auto_accept = False
        if project.threads:
            for t in project.threads.values():
                t.auto_accept = False
        project_manager._save()
        await telegram_queue.reply(message, "Auto-accept reset to ○ off for project and all threads.")
        return

    # /auto_accept - toggle current context
    if thread:
        thread.auto_accept = not thread.auto_accept
        status = "● on" if thread.auto_accept else "○ off"
        await telegram_queue.reply(message, f"Auto-accept: {status}")
    else:
        project.auto_accept = not project.auto_accept
        status = "● on" if project.auto_accept else "○ off"
        await telegram_queue.reply(message, f"Auto-accept: {status}")
    project_manager._save()
```

**Step 2: Test via Telegram MCP**

Send `/auto_accept` and verify response uses circle indicators.

**Step 3: Commit**

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat: update /auto_accept response format with circle indicators"
```

---

## Task 11: Add settings callback handler

**Files:**
- Modify: `src/codogram/handlers/settings.py`
- Test: E2E via Telegram MCP

**Step 1: Add imports for callback handler**

Add to imports at top of `src/codogram/handlers/settings.py`:

```python
from aiogram.types import Message, CallbackQuery
from aiogram import F
```

**Step 2: Add callback handler**

Add callback handler to `src/codogram/handlers/settings.py` (uses `_build_settings_text` from Task 8):

```python
@router.callback_query(F.data.startswith("settings:"))
async def callback_settings(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle settings keyboard button presses."""
    from ..tmux import TmuxSession
    from ..services.session_state import SessionStateService
    from ..keyboards import settings_keyboard

    data = callback.data
    parts = data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    action = parts[1]  # auto_accept, verbose, or mode
    tmux_name = parts[2]

    # Find project by tmux name
    project = project_manager.get_by_tmux(tmux_name)
    if not project:
        await callback.answer("Project not found")
        return

    # Find thread
    thread = None
    for t in project.threads.values():
        if t.get_tmux_session(project.project_name) == tmux_name:
            thread = t
            break

    if action == "auto_accept":
        if thread:
            thread.auto_accept = not thread.auto_accept
            status = "● on" if thread.auto_accept else "○ off"
        else:
            project.auto_accept = not project.auto_accept
            status = "● on" if project.auto_accept else "○ off"
        project_manager._save()
        await callback.answer(f"Auto-accept: {status}")

    elif action == "verbose":
        if thread:
            thread.verbose = not thread.verbose
            status = "● on" if thread.verbose else "○ off"
        else:
            project.verbose = not project.verbose
            status = "● on" if project.verbose else "○ off"
        project_manager._save()
        await callback.answer(f"Verbose: {status}")

    elif action == "mode":
        cwd = thread.worktree_path if thread else project.cwd
        tmux = TmuxSession(tmux_name, cwd)
        service = SessionStateService()
        result = service.cycle_approval_mode(tmux)
        if result.success:
            await callback.answer(f"Mode: {result.new_mode or 'default'}")
        else:
            await callback.answer(result.error)

    # Update the settings message using shared helper
    text = _build_settings_text(project, thread, tmux_name)
    kb = settings_keyboard(tmux_name)
    await telegram_queue.edit(callback.message, text, reply_markup=kb)
```

**Step 3: Add edit method to telegram_queue if needed**

Check if `telegram_queue.edit` exists. If not, add it.

**Step 4: Test via Telegram MCP**

Click settings buttons and verify message updates.

**Step 5: Commit**

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat: add settings callback handler for inline buttons"
```

---

## Task 12: Wire up verbose in history_watcher

**Files:**
- Modify: `src/codogram/history_watcher.py:242-276` (watch_thread_jsonl function)

**Step 1: Update watch_thread_jsonl to pass verbose**

In `src/codogram/history_watcher.py`, update the `watch_thread_jsonl` function (around line 256-258):

```python
async def watch_thread_jsonl(bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue"):
    """Watch jsonl for a specific thread and send messages through queue."""
    from .watcher import JsonlWatcher, _entry_to_messages
    from .telegram_queue import OutgoingBatch
    from pathlib import Path

    if not thread.jsonl_path:
        logger.warning(f"watch_thread_jsonl: no jsonl_path for thread={thread.name}")
        return

    logger.info(f"thread_watcher_started: thread={thread.name}, session={thread.session_id[:8] if thread.session_id else 'None'}")
    watcher = JsonlWatcher(Path(thread.jsonl_path))

    try:
        async for entry in watcher.watch():
            try:
                # Get verbose setting from thread (with fallback to project)
                verbose = thread.verbose if hasattr(thread, 'verbose') else project.verbose
                messages = _entry_to_messages(entry, verbose=verbose)
                if messages:
                    text_preview = messages[0].get("text", "")[:40].replace("\n", " ")
                    msg_id = hash(text_preview) & 0xFFFFFF
                    logger.info(f"message_read: msg_id={msg_id:06x} thread={thread.name} preview='{text_preview}'")

                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread.thread_id,
                        messages=messages,
                    )
                    telegram_ids = await telegram_queue.enqueue(batch)
                    logger.info(f"message_sent: msg_id={msg_id:06x} thread={thread.name} telegram_ids={telegram_ids}")
            except Exception as e:
                logger.error(f"watch_thread_error: {e}")
    except asyncio.CancelledError:
        logger.info(f"watch_thread_cancelled: thread={thread.name}")
        raise
```

The key change is line: `messages = _entry_to_messages(entry, verbose=verbose)`

**Step 2: Test E2E**

1. Run `/verbose` to enable verbose mode
2. Trigger a tool call (send a message to Claude)
3. Verify full body is shown
4. Run `/verbose` again to disable
5. Trigger another tool call
6. Verify body is truncated with `[truncated]`

**Step 3: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "feat: wire verbose setting to history watcher"
```

---

## Task 13: Final E2E testing

**Test cases:**
1. `/settings` shows new format with buttons
2. Click `/auto_accept` button - toggles and updates message
3. Click `/verbose` button - toggles and updates message
4. Click `/shift_tab` button - cycles mode and updates message
5. `/verbose` command toggles setting
6. `/auto_accept` command uses new format
7. With verbose=off, long permission body is truncated
8. With verbose=on, permission body is full
9. Same for tool calls and auto-accept messages

**Commit:**

```bash
git commit --allow-empty -m "test: complete E2E testing for verbose toggle"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add verbose field | session_manager.py |
| 2 | Persist verbose | session_manager.py |
| 3 | truncate_body helper | utils/truncate.py |
| 4 | Apply to permission_poller | permission_poller.py |
| 5 | Apply to auto_accept | auto_accept.py |
| 6 | Apply to watcher | watcher.py |
| 7 | Settings keyboard | keyboards/settings.py |
| 8 | Update /settings | handlers/settings.py |
| 9 | Add /verbose | handlers/settings.py |
| 10 | Update /auto_accept | handlers/settings.py |
| 11 | Settings callbacks | handlers/settings.py |
| 12 | Wire history_watcher | history_watcher.py |
| 13 | E2E testing | - |
