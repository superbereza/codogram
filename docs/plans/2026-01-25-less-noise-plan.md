# Less Noise Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Design:** `docs/plans/2026-01-24-less-noise-design.md`

**Goal:** Reduce visual noise in Telegram bot with granular display control.

**Features:**
1. Verbose mode detailed menu (display_mode enum with 5 modes)
2. Toggle bullet point (on/off for `●` prefix)
3. Thinking text display (show/hide `<thinking>` blocks)
4. Collapsible permission prompts (collapsed by default, expand with pagination)

**Out of Scope:**
- AskUserQuestion — не трогаем в этой итерации

**Tech Stack:** Python 3.12, aiogram 3.x, asyncio

---

## Task 1: Refactor chunker.py - Extract _split_text helper

**Files:**
- Modify: `src/codogram/chunker.py`
- Test: `tests/test_chunker.py`

**Step 1: Write the failing test**

```python
# tests/test_chunker.py
from codogram.chunker import _split_text, chunk_message

def test_split_text_basic():
    """_split_text returns raw chunks without prefixes."""
    text = "Line 1\n\nLine 2\n\nLine 3"
    chunks = _split_text(text, max_len=20)
    # Should split at paragraph breaks
    assert len(chunks) >= 1
    assert "[1/" not in chunks[0]  # No prefix

def test_split_text_single():
    """Single chunk if text fits."""
    text = "Short text"
    chunks = _split_text(text, max_len=100)
    assert chunks == ["Short text"]

def test_chunk_message_adds_prefixes():
    """chunk_message adds [N/M] prefixes for multiple chunks."""
    text = "A" * 100 + "\n\n" + "B" * 100
    chunks = chunk_message(text, max_len=120)
    if len(chunks) > 1:
        assert chunks[0].startswith("[1/")
        assert chunks[1].startswith("[2/")
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_chunker.py -v`
Expected: FAIL with "cannot import name '_split_text'"

**Step 3: Refactor chunker.py**

```python
# src/codogram/chunker.py
from .config import TELEGRAM_MESSAGE_MAX_LENGTH


def _split_text(text: str, max_len: int) -> list[str]:
    """Split text at natural breakpoints (paragraphs -> lines -> sentences).

    Returns raw chunks without prefixes.
    """
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        # Find best split point
        chunk = remaining[:max_len]
        split_at = max_len

        # Try paragraph break
        para = chunk.rfind("\n\n")
        if para > max_len // 2:
            split_at = para + 2
        else:
            # Try line break
            line = chunk.rfind("\n")
            if line > max_len // 2:
                split_at = line + 1
            else:
                # Try sentence
                for sep in (". ", "! ", "? "):
                    pos = chunk.rfind(sep)
                    if pos > max_len // 2:
                        split_at = pos + len(sep)
                        break

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    return chunks


def chunk_message(text: str, max_len: int = TELEGRAM_MESSAGE_MAX_LENGTH) -> list[str]:
    """Split text into chunks with [N/M] prefixes for multi-message sending."""
    # Reserve space for prefix "[N/M]\n" (max ~10 chars)
    prefix_reserve = 10
    chunks = _split_text(text, max_len - prefix_reserve)

    # Add prefixes if multiple chunks
    if len(chunks) > 1:
        chunks = [f"[{i+1}/{len(chunks)}]\n{c}" for i, c in enumerate(chunks)]

    return chunks
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_chunker.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/chunker.py tests/test_chunker.py
git commit -m "refactor(chunker): extract _split_text helper for reuse"
```

---

## Task 2: Data Model - Add display_mode and new fields

**Files:**
- Modify: `src/codogram/core/session_manager.py`
- Modify: `src/codogram/config.py`

**Step 1: Add DisplayMode enum and update ThreadInfo/ProjectState**

In `src/codogram/core/session_manager.py`, add after imports:

```python
from enum import Enum

class DisplayMode(str, Enum):
    """Display mode for tool call output."""
    SHOW_ALL = "show_all"       # Full output without truncation
    LINES = "lines"             # Truncate to N lines (default)
    HEADERS = "headers"         # Only tool headers, no body
    CURRENT = "current"         # Single message, edited with each tool call
    SILENCE = "silence"         # Hide tool calls, show only text responses
```

**Step 2: Update ThreadInfo dataclass**

Replace `verbose: bool = False` with:

```python
    # Display mode (replaces verbose)
    display_mode: str = "lines"     # show_all, lines, headers, current, silence
    line_limit: int = 5             # Used in 'lines' mode
    display_bullet: bool = True     # Show ● prefix
    display_thinking_text: bool = True  # Show <thinking> blocks

    # Rename feat_thinking_status -> working_status
    working_status: bool = False    # Show Claude's working status indicator
```

**Step 3: Update ProjectState dataclass**

Replace `verbose: bool = False` with the same fields:

```python
    # Display mode (replaces verbose, project-wide default)
    display_mode: str = "lines"
    line_limit: int = 5
    display_bullet: bool = True
    display_thinking_text: bool = True

    # Rename feat_thinking_status -> working_status
    working_status: bool = False
```

**Step 4: Update _load_projects migration**

In `_load_projects()`, add migration logic:

```python
# Migration: verbose -> display_mode
if "verbose" in data:
    if data["verbose"]:
        project.display_mode = "show_all"
    else:
        project.display_mode = "lines"
        project.line_limit = 5
    # Don't delete - keep for backward compat during transition

# Migration: feat_thinking_status -> working_status
if "feat_thinking_status" in data:
    project.working_status = data["feat_thinking_status"]
# New fields with defaults
project.display_bullet = data.get("display_bullet", True)
project.display_thinking_text = data.get("display_thinking_text", True)
```

Apply same migration in thread loading:

```python
# In thread_data handling:
if "verbose" in thread_data:
    if thread_data["verbose"]:
        thread.display_mode = "show_all"
    else:
        thread.display_mode = "lines"
        thread.line_limit = 5

if "feat_thinking_status" in thread_data:
    thread.working_status = thread_data["feat_thinking_status"]
thread.display_bullet = thread_data.get("display_bullet", True)
thread.display_thinking_text = thread_data.get("display_thinking_text", True)
```

**Step 5: Update _save() to persist new fields**

In `_save()`, update project_data and thread_data dicts:

```python
# Project level
project_data["display_mode"] = p.display_mode
project_data["line_limit"] = p.line_limit
project_data["display_bullet"] = p.display_bullet
project_data["display_thinking_text"] = p.display_thinking_text
project_data["working_status"] = p.working_status

# Thread level (only if different from default)
if t.display_mode != "lines":
    thread_data["display_mode"] = t.display_mode
if t.line_limit != 5:
    thread_data["line_limit"] = t.line_limit
if not t.display_bullet:
    thread_data["display_bullet"] = t.display_bullet
if not t.display_thinking_text:
    thread_data["display_thinking_text"] = t.display_thinking_text
if t.working_status:
    thread_data["working_status"] = t.working_status
```

**Step 6: Commit**

```bash
git add src/codogram/core/session_manager.py
git commit -m "feat(model): add display_mode, line_limit, display_bullet, display_thinking_text

BREAKING: verbose replaced with display_mode enum
Migration: verbose=true -> show_all, verbose=false -> lines
Rename: feat_thinking_status -> working_status"
```

---

## Task 3: Extract tool_formatter.py from history_watcher.py

**Files:**
- Create: `src/codogram/claude/tool_formatter.py`
- Modify: `src/codogram/claude/history_watcher.py`

**Step 1: Create tool_formatter.py**

```python
# src/codogram/claude/tool_formatter.py
"""Format tool calls for Telegram display."""

from .. import strings
from ..utils.truncate import truncate_body


def format_tool_use(
    tool_name: str,
    tool_input: dict | None,
    display_mode: str = "lines",
    line_limit: int = 5,
    display_bullet: bool = True,
) -> str | None:
    """Format tool use for Telegram display.

    Args:
        tool_name: Name of the tool (Bash, Read, etc.)
        tool_input: Tool input dict
        display_mode: show_all, lines, headers, current, silence
        line_limit: Lines to show in 'lines' mode
        display_bullet: Show ● prefix

    Returns:
        Formatted string or None if should be hidden (silence mode)
    """
    if display_mode == "silence":
        return None

    bullet = "● " if display_bullet else ""

    # Headers mode - just tool name
    if display_mode == "headers":
        return f"{bullet}**{tool_name}**"

    if not tool_input:
        return f"{bullet}**{tool_name}**"

    # Determine verbosity for truncation
    verbose = display_mode == "show_all"

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        char_limit = 3500 if verbose else 500
        was_truncated = len(cmd) > char_limit
        cmd = cmd[:char_limit]
        desc = tool_input.get("description", "")
        cmd_display = truncate_body(cmd, verbose=verbose, max_lines=line_limit) or cmd
        if was_truncated and strings.SNIP not in cmd_display:
            cmd_display += f"\n{strings.SNIP}"
        if desc:
            return f"{bullet}**Bash**: {desc}\n`{cmd_display}`"
        return f"{bullet}**Bash**\n`{cmd_display}`"

    elif tool_name == "Read":
        path = tool_input.get("file_path", "")
        return f"{bullet}**Read** `{path}`"

    elif tool_name == "Write":
        path = tool_input.get("file_path", "")
        return f"{bullet}**Write** `{path}`"

    elif tool_name == "Edit":
        path = tool_input.get("file_path", "")
        return f"{bullet}**Edit** `{path}`"

    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"{bullet}**Glob** `{pattern}`"

    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"{bullet}**Grep** `{pattern}`"

    elif tool_name == "Task":
        desc = tool_input.get("description", "")
        return f"{bullet}**Task**: {desc}"

    elif tool_name == "TodoWrite":
        return f"{bullet}**TodoWrite**"

    else:
        preview_raw = str(tool_input)
        was_truncated = len(preview_raw) > 200
        preview = preview_raw[:200]
        preview = truncate_body(preview, verbose=verbose, max_lines=line_limit) or preview
        if was_truncated and strings.SNIP not in preview:
            preview += f"\n{strings.SNIP}"
        return f"{bullet}**{tool_name}**\n`{preview}`"
```

**Step 2: Update truncate.py to accept max_lines param**

Modify `src/codogram/utils/truncate.py`:

```python
def truncate_body(text: str | None, verbose: bool, max_lines: int = 5) -> str | None:
    """Truncate body text based on verbose setting.

    Args:
        text: Body text to truncate (or None)
        verbose: If True, return full text. If False, truncate to max_lines.
        max_lines: Number of lines to keep when truncating (default 5).

    Returns:
        Truncated text with SNIP suffix, or full text if verbose=True.
    """
    if text is None:
        return None

    if verbose:
        return text

    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text

    truncated = lines[:max_lines]
    while truncated and not truncated[-1].strip():
        truncated.pop()

    return "\n".join(truncated) + f"\n{strings.SNIP}"
```

**Step 3: Update history_watcher.py to use tool_formatter**

In `src/codogram/claude/history_watcher.py`:

```python
from .tool_formatter import format_tool_use

# Remove the local format_tool_use function

# Update _entry_to_messages:
def _entry_to_messages(
    entry: ParsedEntry,
    display_mode: str = "lines",
    line_limit: int = 5,
    display_bullet: bool = True,
) -> list[dict]:
    """Convert ParsedEntry to list of message dicts for queue."""
    messages = []

    if entry.content_type == ContentType.TEXT:
        prefix = "● " if display_bullet else ""
        messages.append({"text": f"{prefix}{entry.text}", "parse_mode": "MarkdownV2"})

    elif entry.content_type == ContentType.TOOL_USE:
        # Hide AskUserQuestion - shown by poller instead
        if entry.tool_name == "AskUserQuestion":
            return []

        text = format_tool_use(
            entry.tool_name,
            entry.tool_input,
            display_mode=display_mode,
            line_limit=line_limit,
            display_bullet=display_bullet,
        )
        if text:  # None in silence mode
            messages.append({"text": text, "parse_mode": "MarkdownV2"})

    return messages
```

**Step 4: Update _watch_with_queue to use new settings**

```python
async def _watch_with_queue(bot: Bot, project, thread, telegram_queue: "TelegramQueue"):
    """Watch jsonl and send entries through queue."""
    from ..telegram.queue import OutgoingBatch
    from pathlib import Path

    if not thread.jsonl_path:
        return

    watcher = JsonlWatcher(Path(thread.jsonl_path))

    try:
        async for entry in watcher.watch():
            try:
                # Get display settings from thread or project
                display_mode = thread.display_mode if hasattr(thread, 'display_mode') else project.display_mode
                line_limit = thread.line_limit if hasattr(thread, 'line_limit') else project.line_limit
                display_bullet = thread.display_bullet if hasattr(thread, 'display_bullet') else project.display_bullet

                messages = _entry_to_messages(
                    entry,
                    display_mode=display_mode,
                    line_limit=line_limit,
                    display_bullet=display_bullet,
                )
                if messages:
                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread.thread_id,
                        messages=messages,
                    )
                    await telegram_queue.enqueue_nowait(batch)
            except Exception as e:
                logger.warning(f"watch_with_queue error: {e}")
    except asyncio.CancelledError:
        raise
```

**Step 5: Commit**

```bash
git add src/codogram/claude/tool_formatter.py src/codogram/claude/history_watcher.py src/codogram/utils/truncate.py
git commit -m "refactor(claude): extract tool_formatter.py with display_mode support"
```

---

## Task 4: Feature 2 - Toggle Bullet Point

**Files:**
- Modify: `src/codogram/handlers/settings.py`
- Modify: `src/codogram/strings.py`

**Step 1: Add command /display_bullet**

In `src/codogram/handlers/settings.py`:

```python
@router.message(Command("display_bullet", ignore_case=True))
async def cmd_display_bullet(message: Message, telegram_queue: TelegramQueue):
    """Toggle bullet point prefix in tool messages."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    if thread:
        thread.display_bullet = not thread.display_bullet
        status = "● on" if thread.display_bullet else "○ off"
    else:
        project.display_bullet = not project.display_bullet
        status = "● on" if project.display_bullet else "○ off"

    project_manager._save()
    await telegram_queue.reply(message, f"Bullet prefix: {status}")
```

**Step 2: Update _build_settings_text**

Add display_bullet to settings display:

```python
def _build_settings_text(project, thread, tmux_name: str) -> str:
    # ... existing code ...

    # Get settings from context
    if thread:
        # ... existing ...
        display_bullet = thread.display_bullet
    else:
        # ... existing ...
        display_bullet = project.display_bullet

    # Format toggle
    bullet_status = "● on" if display_bullet else "○ off"

    # In the ui section:
    lines.append("")
    lines.append("ui")
    lines.append(f"• /display\\_bullet: {bullet_status}")
    # ... rest of settings ...
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat(settings): add /display_bullet toggle"
```

---

## Task 5: Feature 3 - Thinking Text Display

**Files:**
- Modify: `src/codogram/handlers/settings.py`
- Modify: `src/codogram/claude/history_watcher.py`
- Test: manual

**Step 1: Add command /display_thinking_text**

In `src/codogram/handlers/settings.py`:

```python
@router.message(Command("display_thinking_text", ignore_case=True))
async def cmd_display_thinking_text(message: Message, telegram_queue: TelegramQueue):
    """Toggle display of <thinking> blocks in Claude's responses."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    if thread:
        thread.display_thinking_text = not thread.display_thinking_text
        status = "● on" if thread.display_thinking_text else "○ off"
    else:
        project.display_thinking_text = not project.display_thinking_text
        status = "● on" if project.display_thinking_text else "○ off"

    project_manager._save()
    await telegram_queue.reply(message, f"Show thinking blocks: {status}")
```

**Step 2: Add thinking text processing to history_watcher**

Create helper function:

```python
import re

def _process_thinking_text(text: str, display_thinking_text: bool) -> str:
    """Process <thinking> blocks in text response.

    Args:
        text: Claude's text response
        display_thinking_text: If True, show as italic. If False, replace with summary.

    Returns:
        Processed text
    """
    pattern = r'<thinking>(.*?)</thinking>'

    if display_thinking_text:
        # Show as italic, keep tags
        def italicize(match):
            content = match.group(0)
            return f"*{content}*"
        return re.sub(pattern, italicize, text, flags=re.DOTALL)
    else:
        # Replace with summary
        def summarize(match):
            content = match.group(1)
            length = len(content)
            return f"thinked \u2022 {length} symbols"
        return re.sub(pattern, summarize, text, flags=re.DOTALL)
```

**Step 3: Update _entry_to_messages for TEXT content**

```python
def _entry_to_messages(
    entry: ParsedEntry,
    display_mode: str = "lines",
    line_limit: int = 5,
    display_bullet: bool = True,
    display_thinking_text: bool = True,
) -> list[dict]:
    """Convert ParsedEntry to list of message dicts for queue."""
    messages = []

    if entry.content_type == ContentType.TEXT:
        prefix = "● " if display_bullet else ""
        text = entry.text

        # Process thinking blocks
        text = _process_thinking_text(text, display_thinking_text)

        messages.append({"text": f"{prefix}{text}", "parse_mode": "MarkdownV2"})

    # ... rest of function ...
```

**Step 4: Update settings display**

```python
# In _build_settings_text:
thinking_text_status = "● on" if display_thinking_text else "○ off"

lines.append("ui")
lines.append(f"• /display\\_bullet: {bullet_status}")
lines.append(f"• /display\\_thinking\\_text: {thinking_text_status}")
```

**Step 5: Commit**

```bash
git add src/codogram/handlers/settings.py src/codogram/claude/history_watcher.py
git commit -m "feat(settings): add /display_thinking_text toggle"
```

---

## Task 6: Rename feat_thinking_status -> working_status

**Files:**
- Modify: `src/codogram/handlers/settings.py`
- Modify: `src/codogram/claude/poller/processors/thinking.py`
- Modify: `src/codogram/strings.py`

**Step 1: Rename command /exp_thinking_status -> /working_status**

In `src/codogram/handlers/settings.py`:

```python
@router.message(Command("working_status", ignore_case=True))
async def cmd_working_status(message: Message, telegram_queue: TelegramQueue):
    """Toggle working status indicator (Claude's activity)."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    if thread:
        thread.working_status = not thread.working_status
        status = "● on" if thread.working_status else "○ off"
    else:
        project.working_status = not project.working_status
        status = "● on" if project.working_status else "○ off"

    project_manager._save()
    await telegram_queue.reply(message, f"Working status indicator: {status}")


# Keep old command as alias for backward compat
@router.message(Command("exp_thinking_status", ignore_case=True))
async def cmd_exp_thinking_status_alias(message: Message, telegram_queue: TelegramQueue):
    """Alias for /working_status (deprecated)."""
    await cmd_working_status(message, telegram_queue)
```

**Step 2: Update thinking.py processor**

In `src/codogram/claude/poller/processors/thinking.py`, update to use `working_status`:

```python
# Change all occurrences of feat_thinking_status to working_status:
working_status = self.ctx.thread.working_status if self.ctx.thread else self.ctx.project.working_status
```

**Step 3: Update _build_settings_text**

```python
# Change:
# feat_thinking = thread.feat_thinking_status if thread else project.feat_thinking_status
# To:
working = thread.working_status if thread else project.working_status
working_status_display = "● on" if working else "○ off"

# In experimental section:
lines.append("experimental features")
lines.append(f"• /working\\_status: {working_status_display}")
```

**Step 4: Update HELP_TEXT in strings.py**

Replace `/exp_thinking_status` with `/working_status`.

**Step 5: Commit**

```bash
git add src/codogram/handlers/settings.py src/codogram/claude/poller/processors/thinking.py src/codogram/strings.py
git commit -m "refactor(settings): rename feat_thinking_status to working_status

Old command /exp_thinking_status kept as alias for backward compat"
```

---

## Task 7: Modularize handlers/settings - Create directory structure

**Files:**
- Create: `src/codogram/handlers/settings/__init__.py`
- Create: `src/codogram/handlers/settings/main.py`
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Create settings directory**

```bash
mkdir -p src/codogram/handlers/settings
```

**Step 2: Move existing settings.py to settings/main.py**

Move the existing `settings.py` content to `settings/main.py`.

Add TODO comment at the top:
```python
# TODO: модуляризировать - разбить на commands.py, display.py, callbacks.py
```

**Step 3: Create settings/__init__.py**

```python
# src/codogram/handlers/settings/__init__.py
"""Settings handlers - display settings, toggles, verbose menu."""
from aiogram import Router

from .main import router as main_router

router = Router(name="settings")
router.include_router(main_router)

__all__ = ["router"]
```

**Step 4: Update handlers/__init__.py**

Change import from:
```python
from .settings import router as settings_router
```
To:
```python
from .settings import router as settings_router
```
(No change needed if already importing from module)

**Step 5: Commit**

```bash
git add src/codogram/handlers/settings/
git commit -m "refactor(handlers): modularize settings into directory"
```

---

## Task 8: Feature 1 - Verbose Mode Detailed Menu (Part 1: Keyboard)

**Files:**
- Create: `src/codogram/handlers/settings/verbose_menu.py`
- Modify: `src/codogram/handlers/settings/__init__.py`
- Add: `src/codogram/telegram/keyboards/verbose_menu.py`

**Step 1: Create verbose_menu keyboard**

```python
# src/codogram/telegram/keyboards/verbose_menu.py
"""Verbose mode menu keyboard."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def verbose_menu_keyboard(
    current_mode: str,
    line_limit: int,
    short_id: str,
) -> InlineKeyboardMarkup:
    """Build verbose mode menu keyboard.

    Args:
        current_mode: Current display mode
        line_limit: Current line limit (for 'lines' mode)
        short_id: Short identifier for callback data

    Returns:
        Inline keyboard with mode selection buttons
    """
    buttons = []

    # Mode buttons
    buttons.append([
        InlineKeyboardButton(
            text="show all" if current_mode != "show_all" else "[show all]",
            callback_data=f"vm:{short_id}:mode:show_all"
        )
    ])

    # Lines mode with +/- controls
    lines_text = f"lines: {line_limit}" if current_mode == "lines" else f"lines ({line_limit})"
    buttons.append([
        InlineKeyboardButton(text="-5", callback_data=f"vm:{short_id}:lines:-5"),
        InlineKeyboardButton(
            text=f"[{lines_text}]" if current_mode == "lines" else lines_text,
            callback_data=f"vm:{short_id}:mode:lines"
        ),
        InlineKeyboardButton(text="+5", callback_data=f"vm:{short_id}:lines:+5"),
    ])

    buttons.append([
        InlineKeyboardButton(
            text="headers only" if current_mode != "headers" else "[headers only]",
            callback_data=f"vm:{short_id}:mode:headers"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="only current" if current_mode != "current" else "[only current]",
            callback_data=f"vm:{short_id}:mode:current"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="total silence" if current_mode != "silence" else "[total silence]",
            callback_data=f"vm:{short_id}:mode:silence"
        )
    ])

    buttons.append([
        InlineKeyboardButton(text="close", callback_data=f"vm:{short_id}:close")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

**Step 2: Add to keyboards/__init__.py**

```python
from .verbose_menu import verbose_menu_keyboard

__all__ = [
    # ... existing ...
    "verbose_menu_keyboard",
]
```

**Step 3: Create verbose_menu.py handler**

```python
# src/codogram/handlers/settings/verbose_menu.py
"""Verbose mode detailed menu."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from ...core.session_manager import project_manager, DisplayMode
from ...telegram.queue import TelegramQueue
from ...telegram.keyboards.verbose_menu import verbose_menu_keyboard
from ...telegram.keyboards.settings import _short_id

router = Router(name="verbose_menu")

MODE_DESCRIPTIONS = {
    "show_all": "Full output without truncation",
    "lines": "Truncate tool output to {limit} lines",
    "headers": "Show tool headers only, no body",
    "current": "Single message, updated with each tool call",
    "silence": "Hide tool calls, show only Claude's text responses",
}


def _build_verbose_text(display_mode: str, line_limit: int) -> str:
    """Build verbose menu message text."""
    desc = MODE_DESCRIPTIONS.get(display_mode, "").format(limit=line_limit)
    return f"""**Verbose mode**
Current: {display_mode}{f' ({line_limit})' if display_mode == 'lines' else ''}
{desc}"""


@router.message(Command("verbose_mode", ignore_case=True))
async def cmd_verbose_mode(message: Message, telegram_queue: TelegramQueue):
    """Show verbose mode menu."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    # Get current settings
    if thread:
        display_mode = thread.display_mode
        line_limit = thread.line_limit
        tmux_name = thread.get_tmux_session(project.project_name)
    else:
        display_mode = project.display_mode
        line_limit = project.line_limit
        tmux_name = f"claude-{project.project_name}"

    text = _build_verbose_text(display_mode, line_limit)
    kb = verbose_menu_keyboard(display_mode, line_limit, _short_id(tmux_name))

    await telegram_queue.reply(message, text, reply_markup=kb)


@router.callback_query(F.data.startswith("vm:"))
async def callback_verbose_menu(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle verbose menu button presses."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    short_id = parts[1]
    action = parts[2]

    # Find project and thread by short ID
    project = None
    thread = None
    tmux_name = None

    for p in project_manager.projects.values():
        for t in p.threads.values():
            t_tmux = t.get_tmux_session(p.project_name)
            if _short_id(t_tmux) == short_id:
                project = p
                thread = t
                tmux_name = t_tmux
                break
        if project:
            break
        p_tmux = f"claude-{p.project_name}"
        if _short_id(p_tmux) == short_id:
            project = p
            tmux_name = p_tmux
            break

    if not project:
        await callback.answer("Project not found")
        return

    if action == "close":
        await callback.message.delete()
        await callback.answer()
        return

    if action == "mode":
        if len(parts) < 4:
            await callback.answer("Invalid mode")
            return
        new_mode = parts[3]
        if thread:
            thread.display_mode = new_mode
        else:
            project.display_mode = new_mode
        project_manager._save()
        await callback.answer(f"Mode: {new_mode}")

    elif action == "lines":
        if len(parts) < 4:
            await callback.answer("Invalid action")
            return
        delta = int(parts[3])
        if thread:
            thread.line_limit = max(1, thread.line_limit + delta)
            line_limit = thread.line_limit
        else:
            project.line_limit = max(1, project.line_limit + delta)
            line_limit = project.line_limit
        project_manager._save()
        await callback.answer(f"Lines: {line_limit}")

    # Update message
    display_mode = thread.display_mode if thread else project.display_mode
    line_limit = thread.line_limit if thread else project.line_limit

    text = _build_verbose_text(display_mode, line_limit)
    kb = verbose_menu_keyboard(display_mode, line_limit, short_id)

    await telegram_queue.edit(callback.message, text, reply_markup=kb)
```

**Step 4: Update settings/__init__.py**

```python
from .main import router as main_router
from .verbose_menu import router as verbose_menu_router

router = Router(name="settings")
router.include_router(main_router)
router.include_router(verbose_menu_router)
```

**Step 5: Commit**

```bash
git add src/codogram/handlers/settings/verbose_menu.py src/codogram/telegram/keyboards/verbose_menu.py
git commit -m "feat(verbose): add detailed verbose mode menu with display modes"
```

---

## Task 9: Feature 1 - Verbose Mode (Part 2: "current" mode implementation)

**Files:**
- Modify: `src/codogram/claude/history_watcher.py`

**Step 1: Add state tracking for "current" mode**

In `_watch_with_queue`, add state for "current" mode:

```python
async def _watch_with_queue(bot: Bot, project, thread, telegram_queue: "TelegramQueue"):
    """Watch jsonl and send entries through queue."""
    from ..telegram.queue import OutgoingBatch, EditBatch

    if not thread.jsonl_path:
        return

    watcher = JsonlWatcher(Path(thread.jsonl_path))

    # State for "current" mode
    current_mode_key = f"current:{project.chat_id}:{thread.thread_id}"
    last_tool_text: str | None = None

    try:
        async for entry in watcher.watch():
            try:
                display_mode = getattr(thread, 'display_mode', getattr(project, 'display_mode', 'lines'))
                line_limit = getattr(thread, 'line_limit', getattr(project, 'line_limit', 5))
                display_bullet = getattr(thread, 'display_bullet', getattr(project, 'display_bullet', True))
                display_thinking_text = getattr(thread, 'display_thinking_text', True)

                messages = _entry_to_messages(
                    entry,
                    display_mode=display_mode,
                    line_limit=line_limit,
                    display_bullet=display_bullet,
                    display_thinking_text=display_thinking_text,
                )

                if not messages:
                    continue

                if display_mode == "current" and entry.content_type == ContentType.TOOL_USE:
                    # In "current" mode, edit single message
                    text = messages[0]["text"]

                    if last_tool_text is None:
                        # First tool - send new message
                        batch = OutgoingBatch(
                            chat_id=project.chat_id,
                            thread_id=thread.thread_id,
                            messages=messages,
                            replace_key=current_mode_key,
                        )
                        await telegram_queue.enqueue_nowait(batch)
                    else:
                        # Edit existing message
                        batch = EditBatch(
                            chat_id=project.chat_id,
                            message_id=0,  # Lookup from sent_statuses
                            text=text,
                            replace_key=current_mode_key,
                        )
                        await telegram_queue.enqueue_nowait(batch)

                    last_tool_text = text
                else:
                    # Normal mode - send as usual
                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread.thread_id,
                        messages=messages,
                    )
                    await telegram_queue.enqueue_nowait(batch)

                    # Reset current mode state on non-tool message
                    if entry.content_type == ContentType.TEXT:
                        last_tool_text = None

            except Exception as e:
                logger.warning(f"watch_with_queue error: {e}")
    except asyncio.CancelledError:
        raise
```

**Step 2: Commit**

```bash
git add src/codogram/claude/history_watcher.py
git commit -m "feat(verbose): implement 'current' display mode - single editable message"
```

---

## Task 10: Feature 4 - Collapsible Permission Prompts (Part 1: Data structure)

**Files:**
- Modify: `src/codogram/state.py`
- Modify: `src/codogram/claude/poller/processors/permissions.py`

**Step 1: Add PermissionPromptState to state.py**

```python
# src/codogram/state.py
from dataclasses import dataclass, field

@dataclass
class PermissionPromptState:
    """State for a permission prompt message."""
    tmux_name: str
    body: str
    options: list[str]
    expanded: bool = False
    current_page: int = 0
    chunks: list[str] = field(default_factory=list)


# Replace permission_messages with permission_states
# permission_messages: dict[int, list[int]] = {}  # REMOVE - no longer needed
permission_states: dict[int, PermissionPromptState] = {}  # msg_id -> state
```

**Step 2: Update PermissionProcessor state**

```python
class PermissionProcessor(BaseProcessor):
    """Handles permission prompts with debounce and state machine."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.state = PermissionState.IDLE
        self.debounce_start: float = 0.0
        self.last_options: list[str] | None = None
        self.last_body: str | None = None

        # Single message approach (replaces content_msg_ids + kb_msg_id)
        self.msg_id: int | None = None
        self.expanded: bool = False
        self.current_page: int = 0
        self.chunks: list[str] | None = None  # Body chunks for pagination
```

**Step 2: Remove old message tracking fields**

Remove:
- `self.content_msg_ids: list[int] = []`
- `self.kb_msg_id: int | None = None`

**Step 3: Commit**

```bash
git add src/codogram/claude/poller/processors/permissions.py
git commit -m "refactor(permissions): update state for single message approach"
```

---

## Task 11: Feature 4 - Collapsible Permission Prompts (Part 2: Keyboard)

**Files:**
- Modify: `src/codogram/telegram/keyboards/permissions.py`

**Step 1: Update permission_keyboard to support collapsed/expanded states**

```python
# src/codogram/telegram/keyboards/permissions.py
"""Permission prompt keyboards."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def permission_keyboard(
    options: list[str],
    tmux_name: str,
    expanded: bool = False,
    current_page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """Build permission prompt keyboard.

    Args:
        options: Permission options (e.g., ["[1] Allow once...", ...])
        tmux_name: Tmux session name for callback routing
        expanded: Whether body is expanded
        current_page: Current page index (0-based)
        total_pages: Total number of pages

    Returns:
        Inline keyboard with option buttons and expand/collapse controls
    """
    buttons = []

    # Expand/collapse and pagination controls
    if expanded and total_pages > 1:
        # Show pagination: [<] [>]
        nav_row = []
        if current_page > 0:
            nav_row.append(InlineKeyboardButton(
                text="\u25c0",  # ◀
                callback_data=f"perm:{tmux_name}:page:{current_page - 1}"
            ))
        if current_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="\u25b6",  # ▶
                callback_data=f"perm:{tmux_name}:page:{current_page + 1}"
            ))
        if nav_row:
            buttons.append(nav_row)

    # Expand/collapse button
    if expanded:
        buttons.append([InlineKeyboardButton(
            text="Show less",
            callback_data=f"perm:{tmux_name}:collapse"
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text="Show more",
            callback_data=f"perm:{tmux_name}:expand"
        )])

    # Option buttons (numbered)
    option_row = []
    for i, opt in enumerate(options):
        option_row.append(InlineKeyboardButton(
            text=f"[{i + 1}]",
            callback_data=f"perm:{tmux_name}:{i + 1}"
        ))
    buttons.append(option_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

**Step 2: Commit**

```bash
git add src/codogram/telegram/keyboards/permissions.py
git commit -m "feat(permissions): update keyboard for collapsed/expanded states with pagination"
```

---

## Task 12: Feature 4 - Collapsible Permission Prompts (Part 3: Collapsed UI)

**Files:**
- Modify: `src/codogram/claude/poller/processors/permissions.py`
- Use: `src/codogram/chunker.py`

**Step 1: Import _split_text and permission_states**

```python
from ....chunker import _split_text
from ....state import permission_states, PermissionPromptState

PERMISSION_PAGE_SIZE = 2000  # Characters per page
```

**Step 2: Rewrite _send_permission for single message**

```python
async def _send_permission(self, parsed: PermissionPrompt, verbose: bool) -> None:
    """Send permission prompt as single collapsible message."""
    try:
        # Build message text (collapsed by default)
        text = self._build_permission_text(parsed, collapsed=True)

        # Build keyboard (no pagination needed when collapsed)
        kb = permission_keyboard(
            parsed.options,
            self.ctx.tmux_name,
            expanded=False,
            current_page=0,
            total_pages=1,
        )

        # Send single message
        batch = OutgoingBatch(
            chat_id=self.ctx.chat_id,
            thread_id=self.ctx.thread_id,
            messages=[{"text": text}],
            reply_markup=kb,
        )
        msg_ids = await self.ctx.queue.enqueue(batch)

        self.msg_id = msg_ids[0] if msg_ids else None

        # Save state for callback handlers
        if self.msg_id:
            permission_states[self.msg_id] = PermissionPromptState(
                tmux_name=self.ctx.tmux_name,
                body=parsed.body or "",
                options=parsed.options,
                expanded=False,
                current_page=0,
                chunks=[],  # Computed lazily on expand
            )

        self.state = PermissionState.SHOWING
        self.last_body = parsed.body
        self.log_debug(f"SHOWING: sent collapsed prompt, msg={self.msg_id}")

    except Exception as e:
        self.log_warning(f"send error: {e}")
        self.state = PermissionState.IDLE


def _build_permission_text(self, parsed: PermissionPrompt, collapsed: bool) -> str:
    """Build permission prompt message text.

    Args:
        parsed: Parsed permission prompt
        collapsed: If True, show only header. If False, show body page.

    Returns:
        Formatted message text
    """
    # Header: tool name + brief description
    header = self._get_prompt_header(parsed)

    if collapsed:
        # Collapsed: header + options
        lines = [header, ""]
        lines.extend(parsed.options)
        return "\n".join(lines)

    # Expanded: header + body page + options
    lines = [header, "", SEPARATOR_SOLID]

    if self.chunks:
        # Show current page with indicator
        total = len(self.chunks)
        if total > 1:
            lines.append(f"[{self.current_page + 1}/{total}] {self.chunks[self.current_page]}")
        else:
            lines.append(self.chunks[self.current_page])

    lines.append(SEPARATOR_SOLID)
    lines.append("")
    lines.extend(parsed.options)

    return "\n".join(lines)


def _get_prompt_header(self, parsed: PermissionPrompt) -> str:
    """Extract brief header from permission prompt body."""
    if not parsed.body:
        return "Permission request"

    # Try to extract tool name and brief description from first line
    first_line = parsed.body.split("\n")[0][:60]
    return first_line if first_line else "Permission request"
```

**Step 3: Update _cleanup_messages for single message**

```python
async def _cleanup_messages(self) -> None:
    """Delete permission message and state."""
    if self.msg_id:
        # Remove state
        permission_states.pop(self.msg_id, None)
        # Delete message
        try:
            await self.ctx.bot.delete_message(self.ctx.chat_id, self.msg_id)
        except Exception:
            pass
        self.msg_id = None
```

**Step 4: Update _reset_state**

```python
def _reset_state(self) -> None:
    self.state = PermissionState.IDLE
    self.last_options = None
    self.last_body = None
    self.msg_id = None
    self.expanded = False
    self.current_page = 0
    self.chunks = None
```

**Step 5: Commit**

```bash
git add src/codogram/claude/poller/processors/permissions.py
git commit -m "feat(permissions): implement collapsed UI with single message"
```

---

## Task 13: Feature 4 - Collapsible Permission Prompts (Part 4: Callbacks)

**Files:**
- Modify: `src/codogram/handlers/permissions.py`

**Step 1: Update permission callbacks to use permission_states**

```python
# In handlers/permissions.py
from ..state import permission_states, PermissionPromptState
from ..chunker import _split_text

PERMISSION_PAGE_SIZE = 2000


def _build_permission_text(state: PermissionPromptState) -> str:
    """Build permission prompt message text from state."""
    # Header from first line of body
    header = state.body.split("\n")[0][:60] if state.body else "Permission request"

    if not state.expanded:
        # Collapsed: header + options
        lines = [header, ""]
        lines.extend(state.options)
        return "\n".join(lines)

    # Expanded: header + body page + options
    lines = [header, "", "────────────"]

    if state.chunks:
        total = len(state.chunks)
        if total > 1:
            lines.append(f"[{state.current_page + 1}/{total}] {state.chunks[state.current_page]}")
        else:
            lines.append(state.chunks[state.current_page])

    lines.append("────────────")
    lines.append("")
    lines.extend(state.options)

    return "\n".join(lines)


@router.callback_query(F.data.startswith("perm:"))
async def callback_permission(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle permission button presses."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    tmux_name = parts[1]
    action = parts[2]

    # Find state by message_id
    msg_id = callback.message.message_id
    state = permission_states.get(msg_id)

    if not state:
        # Stale prompt (bot restarted or message expired)
        await callback.message.delete()
        await callback.answer("Prompt expired")
        return

    # Verify tmux_name matches
    if state.tmux_name != tmux_name:
        await callback.message.delete()
        await callback.answer("Stale prompt")
        return

    if action == "expand":
        state.expanded = True
        state.current_page = 0
        # Compute chunks if not already
        if not state.chunks and state.body:
            state.chunks = _split_text(state.body, max_len=PERMISSION_PAGE_SIZE)
        await _update_permission_message(callback, state, telegram_queue)
        await callback.answer()

    elif action == "collapse":
        state.expanded = False
        await _update_permission_message(callback, state, telegram_queue)
        await callback.answer()

    elif action == "page":
        if len(parts) < 4:
            await callback.answer("Invalid page")
            return
        state.current_page = int(parts[3])
        await _update_permission_message(callback, state, telegram_queue)
        await callback.answer()

    else:
        # Option selection (1, 2, 3, etc.) - send key to tmux
        try:
            option_num = int(action)
            # Find project and send key
            project = project_manager.get_by_tmux(tmux_name)
            if project and project.cwd:
                tmux = TmuxSession(tmux_name, project.cwd)
                if tmux.exists():
                    # Send the option key (e.g., "1", "2", "y", "n")
                    key = state.options[option_num - 1].split("]")[0].lstrip("[") if option_num <= len(state.options) else str(option_num)
                    tmux.send_key(key)

            # Cleanup
            permission_states.pop(msg_id, None)
            await callback.message.delete()
            await callback.answer()
        except (ValueError, IndexError):
            await callback.answer("Invalid option")


async def _update_permission_message(
    callback: CallbackQuery,
    state: PermissionPromptState,
    telegram_queue: TelegramQueue,
) -> None:
    """Update permission message with new state."""
    from ..telegram.keyboards import permission_keyboard

    text = _build_permission_text(state)

    total_pages = len(state.chunks) if state.chunks else 1
    kb = permission_keyboard(
        state.options,
        state.tmux_name,
        expanded=state.expanded,
        current_page=state.current_page,
        total_pages=total_pages,
    )

    await telegram_queue.edit(callback.message, text, reply_markup=kb)
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/permissions.py src/codogram/claude/poller/processors/permissions.py
git commit -m "feat(permissions): add expand/collapse/page callbacks"
```

---

## Task 14: Update Settings UI - Add new fields to display

**Files:**
- Modify: `src/codogram/handlers/settings/main.py`

**Step 1: Update _build_settings_text with full UI from design**

```python
def _build_settings_text(project, thread, tmux_name: str) -> str:
    """Build settings message text."""
    from ..tmux.session import TmuxSession
    from ..services.session_state import SessionStateService

    # Get settings from context
    if thread:
        auto_accept = thread.auto_accept
        display_mode = getattr(thread, 'display_mode', 'lines')
        line_limit = getattr(thread, 'line_limit', 5)
        display_bullet = getattr(thread, 'display_bullet', True)
        display_thinking_text = getattr(thread, 'display_thinking_text', True)
        working_status = getattr(thread, 'working_status', False)
        context_name = thread.name
        cwd = thread.worktree_path or project.cwd
        response_mode = thread.response_mode
    else:
        auto_accept = project.auto_accept
        display_mode = getattr(project, 'display_mode', 'lines')
        line_limit = getattr(project, 'line_limit', 5)
        display_bullet = getattr(project, 'display_bullet', True)
        display_thinking_text = getattr(project, 'display_thinking_text', True)
        working_status = getattr(project, 'working_status', False)
        context_name = project.project_name
        cwd = project.cwd
        response_mode = project.response_mode

    # Format toggle indicators
    auto_status = "● on" if auto_accept else "○ off"
    bullet_status = "● on" if display_bullet else "○ off"
    thinking_status = "● on" if display_thinking_text else "○ off"
    working_status_text = "● on" if working_status else "○ off"

    # Format display_mode
    if display_mode == "lines":
        verbose_status = f"lines ({line_limit})"
    else:
        verbose_status = display_mode

    # Experimental features (project-level)
    suggestions_status = "● on" if project.feat_suggestions else "○ off"
    avatar_pack_status = "● on" if project.feat_avatar_pack else "○ off"

    lines = [f"**{context_name}**", ""]

    # Chat section
    lines.append("chat")
    lines.append(f"• /auto\\_accept: {auto_status}")
    lines.append(f"• /response\\_mode: {response_mode}")

    # Claude section
    lines.append("")
    lines.append("claude")

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
            if sb.approval_mode == "accept edits":
                mode_text = "⏵⏵ accept edits"
            elif sb.approval_mode == "plan mode":
                mode_text = "⏸ plan mode"
            else:
                mode_text = "default"
            lines.append(f"• mode: {mode_text}")
            lines.append("  (use /shift\\_tab to cycle)")
            lines.append(f"• background tasks: {sb.background_tasks}")
            if sb.context_percent is not None:
                lines.append(f"• context: {sb.context_percent}%")
            else:
                lines.append("• context: not displayed")
    else:
        lines.append("• mode: not connected")
        lines.append("• background tasks: ?")
        lines.append("• context: ?")

    # UI section
    lines.append("")
    lines.append("ui")
    lines.append(f"• /verbose: {verbose_status}")
    lines.append(f"• /display\\_bullet: {bullet_status}")
    lines.append(f"• /display\\_thinking\\_text: {thinking_status}")

    # Experimental section
    lines.append("")
    lines.append("experimental features")
    lines.append(f"• /working\\_status: {working_status_text}")
    lines.append(f"• /exp\\_suggestions: {suggestions_status}")
    lines.append(f"• /exp\\_avatar\\_pack: {avatar_pack_status}")

    return "\n".join(lines)
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/settings/main.py
git commit -m "feat(settings): update settings display with new ui section"
```

---

## Task 15: Settings Button Pagination

**Files:**
- Modify: `src/codogram/handlers/settings/main.py`
- Modify: `src/codogram/telegram/keyboards/settings.py`

**Step 1: Create paginated settings keyboard**

```python
# src/codogram/telegram/keyboards/settings.py

SETTINGS_BUTTON_GROUPS = [
    # Group 0: chat
    ["/auto_accept", "/response_mode"],
    # Group 1: ui
    ["/verbose_mode", "/display_bullet", "/display_thinking_text"],
    # Group 2: experimental
    ["/working_status", "/exp_suggestions", "/exp_avatar_pack"],
]


def settings_keyboard(tmux_name: str, page: int = 0) -> InlineKeyboardMarkup:
    """Build paginated settings keyboard.

    Args:
        tmux_name: Tmux session name for callback routing
        page: Current page (0-based)

    Returns:
        Inline keyboard with current group buttons + navigation
    """
    buttons = []

    group = SETTINGS_BUTTON_GROUPS[page]
    for cmd in group:
        buttons.append([InlineKeyboardButton(
            text=cmd,
            callback_data=f"set:{tmux_name}:{cmd.lstrip('/')}"
        )])

    # Navigation row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            text="<",
            callback_data=f"settings:{tmux_name}:page:{page - 1}"
        ))
    if page < len(SETTINGS_BUTTON_GROUPS) - 1:
        nav_row.append(InlineKeyboardButton(
            text=">",
            callback_data=f"settings:{tmux_name}:page:{page + 1}"
        ))
    if nav_row:
        buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

**Step 2: Add page callback handler**

In `src/codogram/handlers/settings/main.py`:

```python
@router.callback_query(F.data.startswith("settings:") & F.data.contains(":page:"))
async def callback_settings_page(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle settings page navigation."""
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Invalid callback")
        return

    tmux_name = parts[1]
    new_page = int(parts[3])

    # Rebuild keyboard with new page
    kb = settings_keyboard(tmux_name, page=new_page)

    # Edit message (text stays same, only keyboard changes)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()
```

**Step 3: Update cmd_settings to use paginated keyboard**

```python
@router.message(Command("settings", ignore_case=True))
async def cmd_settings(message: Message, telegram_queue: TelegramQueue):
    # ... existing code to build text ...

    kb = settings_keyboard(tmux_name, page=0)  # Start at page 0
    await telegram_queue.reply(message, text, reply_markup=kb)
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/settings/main.py src/codogram/telegram/keyboards/settings.py
git commit -m "feat(settings): add button pagination with [<] [>] navigation"
```

---

## Task 16: E2E Testing

**Files:**
- Add test cases to `docs/e2e/commands/settings.md`

**Step 1: Create E2E test document**

```markdown
# E2E Tests: Less Noise Features

## TC-NOISE-001: Verbose Mode Menu

**Precondition:** Project registered, Claude running

**Steps:**
1. Send `/verbose`
2. Observe menu message with current mode

**Expected:**
- Message shows "Verbose mode" with current setting
- Buttons: [show all], [-5] [lines: N] [+5], [headers only], [only current], [total silence], [close]

## TC-NOISE-002: Change Display Mode

**Precondition:** /verbose menu open

**Steps:**
1. Click [headers only] button
2. Observe update

**Expected:**
- Button becomes [headers only] (selected)
- Mode description updates
- Toast shows "Mode: headers"

## TC-NOISE-003: Bullet Toggle

**Steps:**
1. Send `/display_bullet`
2. Observe response

**Expected:**
- Response shows "Bullet prefix: ○ off" or "● on"
- Tool messages now show/hide ● prefix

## TC-NOISE-004: Thinking Text Toggle

**Steps:**
1. Send `/display_thinking_text`
2. Trigger Claude response with <thinking> block

**Expected:**
- When ON: shows *<thinking>...*</thinking>* (italic)
- When OFF: shows "thinked • N symbols"

## TC-NOISE-005: Collapsible Permission Prompt

**Precondition:** Auto-accept OFF

**Steps:**
1. Trigger permission prompt (e.g., file write)
2. Observe collapsed view

**Expected:**
- Single message with header + options
- [Show more] button visible
- Option buttons [1] [2] [3]

## TC-NOISE-006: Expand Permission Prompt

**Precondition:** Collapsed permission prompt showing

**Steps:**
1. Click [Show more]
2. Observe expanded view

**Expected:**
- Body content now visible with separator
- [Show less] button replaces [Show more]
- If long content: [◀] [▶] pagination buttons

## TC-NOISE-007: Permission Pagination

**Precondition:** Expanded prompt with multiple pages

**Steps:**
1. Click [▶] button
2. Click [◀] button

**Expected:**
- Content changes to next/prev page
- Page indicator updates [1/3] -> [2/3]
```

**Step 2: Run E2E tests manually using Telegram MCP**

Ask user for test chat ID, then execute test cases.

**Step 3: Final commit**

```bash
git add docs/e2e/commands/settings.md
git commit -m "docs: add E2E tests for less-noise features"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Extract _split_text helper | chunker.py |
| 2 | Add display_mode and new fields to data model | session_manager.py |
| 3 | Extract tool_formatter.py | claude/tool_formatter.py, history_watcher.py |
| 4 | Feature 2: Bullet toggle | handlers/settings.py |
| 5 | Feature 3: Thinking text display | handlers/settings.py, history_watcher.py |
| 6 | Rename feat_thinking_status -> working_status | settings.py, thinking.py, strings.py |
| 7 | Modularize handlers/settings | handlers/settings/ |
| 8 | Feature 1: Verbose menu keyboard | settings/verbose_menu.py |
| 9 | Feature 1: "current" mode implementation | history_watcher.py |
| 10 | Feature 4: Permission processor state | state.py, permissions.py |
| 11 | Feature 4: Permission keyboard | keyboards/permissions.py |
| 12 | Feature 4: Collapsed UI | permissions.py |
| 13 | Feature 4: Callbacks | handlers/permissions.py |
| 14 | Update settings display | settings/main.py |
| 15 | Settings button pagination | settings/main.py, keyboards/settings.py |
| 16 | E2E testing | docs/e2e/ |
