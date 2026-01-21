# AskUserQuestion Support + Poller Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Добавить поддержку AskUserQuestion через poller + рефакторинг 600-строчного poller.py в модульную структуру.

**Architecture:** Разбиваем monolithic `claude/poller.py` на `claude/poller/` package с отдельными processors. Добавляем детекцию AskUserQuestion в `screen.py`, новый `AskUserQuestionProcessor`, keyboard и callback handler.

**Tech Stack:** Python 3.12, aiogram 3.x, asyncio

---

## Phase 1: Poller Refactoring

### Task 1: Create poller package structure

**Files:**
- Create: `src/codogram/claude/poller/__init__.py`
- Create: `src/codogram/claude/poller/context.py`
- Create: `src/codogram/claude/poller/base.py`

**Step 1: Create directory and __init__.py**

```bash
mkdir -p src/codogram/claude/poller/processors
```

**Step 2: Create context.py**

```python
# src/codogram/claude/poller/context.py
"""Shared context for all poller processors."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram import Bot

if TYPE_CHECKING:
    from ...telegram.queue import TelegramQueue
    from ...core.session_manager import ProjectState, ThreadInfo
    from ...tmux.session import TmuxSession


@dataclass
class PollerContext:
    """Shared context passed to all processors."""
    bot: Bot
    project: "ProjectState"
    thread: "ThreadInfo | None"
    tmux: "TmuxSession"
    queue: "TelegramQueue"
    chat_id: int
    thread_id: int | None
    log_prefix: str
    context_name: str
    tmux_name: str
```

**Step 3: Create base.py**

```python
# src/codogram/claude/poller/base.py
"""Base processor class with common helpers."""
from typing import TYPE_CHECKING

from ...telegram.queue import OutgoingBatch, EditBatch, DeleteBatch
from ...logging_config import logger

if TYPE_CHECKING:
    from .context import PollerContext


class BaseProcessor:
    """Base class for all poller processors."""

    def __init__(self, ctx: "PollerContext"):
        self.ctx = ctx

    async def process(self, screen: str) -> None:
        """Process screen content. Override in subclasses."""
        raise NotImplementedError

    async def send(self, text: str, parse_mode: str | None = None, **kwargs) -> list[int]:
        """Send message via queue."""
        messages = [{"text": text}]
        if parse_mode:
            messages[0]["parse_mode"] = parse_mode
        batch = OutgoingBatch(
            chat_id=self.ctx.chat_id,
            thread_id=self.ctx.thread_id,
            messages=messages,
            **kwargs,
        )
        return await self.ctx.queue.enqueue(batch)

    async def send_nowait(self, text: str, parse_mode: str | None = None, **kwargs) -> None:
        """Send message without waiting for result."""
        messages = [{"text": text}]
        if parse_mode:
            messages[0]["parse_mode"] = parse_mode
        batch = OutgoingBatch(
            chat_id=self.ctx.chat_id,
            thread_id=self.ctx.thread_id,
            messages=messages,
            **kwargs,
        )
        await self.ctx.queue.enqueue_nowait(batch)

    async def edit_by_key(self, text: str, key: str) -> None:
        """Edit message by replace_key."""
        batch = EditBatch(
            chat_id=self.ctx.chat_id,
            message_id=0,
            text=text,
            replace_key=key,
        )
        await self.ctx.queue.enqueue_nowait(batch)

    async def delete_by_key(self, key: str) -> None:
        """Delete message by replace_key."""
        batch = DeleteBatch(
            chat_id=self.ctx.chat_id,
            message_id=0,
            replace_key=key,
        )
        await self.ctx.queue.enqueue_nowait(batch)

    def log_debug(self, msg: str) -> None:
        """Log debug message with prefix."""
        logger.debug(f"{self.ctx.log_prefix}: {msg}")

    def log_info(self, msg: str) -> None:
        """Log info message with prefix."""
        logger.info(f"{self.ctx.log_prefix}: {msg}")

    def log_warning(self, msg: str) -> None:
        """Log warning message with prefix."""
        logger.warning(f"{self.ctx.log_prefix}: {msg}")
```

**Step 4: Create __init__.py with re-exports**

```python
# src/codogram/claude/poller/__init__.py
"""Poller package - background permission and status polling."""
from .context import PollerContext
from .base import BaseProcessor

__all__ = ["PollerContext", "BaseProcessor"]
```

**Step 5: Commit**

```bash
git add src/codogram/claude/poller/
git commit -m "refactor(poller): create poller package structure with context and base"
```

---

### Task 2: Create CompactProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/__init__.py`
- Create: `src/codogram/claude/poller/processors/compact.py`

**Step 1: Create processors/__init__.py**

```python
# src/codogram/claude/poller/processors/__init__.py
"""Poller processors - each handles one concern."""
from .compact import CompactProcessor

__all__ = ["CompactProcessor"]
```

**Step 2: Create compact.py**

```python
# src/codogram/claude/poller/processors/compact.py
"""Compact notification processor."""
from ..base import BaseProcessor
from ...screen import detect_compacting
from .... import strings


class CompactProcessor(BaseProcessor):
    """Sends one-time notification when Claude starts compacting."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.notified: bool = False

    async def process(self, screen: str) -> None:
        is_compacting = detect_compacting(screen)

        if is_compacting and not self.notified:
            self.log_info("compact detected, sending notification")
            await self.send_nowait(strings.COMPACTING_STARTED, parse_mode="MarkdownV2")
            self.notified = True
        elif not is_compacting:
            self.notified = False
```

**Step 3: Update processors/__init__.py**

Already done in step 1.

**Step 4: Commit**

```bash
git add src/codogram/claude/poller/processors/
git commit -m "refactor(poller): extract CompactProcessor"
```

---

### Task 3: Create ThinkingProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/thinking.py`
- Modify: `src/codogram/claude/poller/processors/__init__.py`

**Step 1: Create thinking.py**

```python
# src/codogram/claude/poller/processors/thinking.py
"""Thinking status display processor."""
import asyncio
from ..base import BaseProcessor
from ...screen import parse_thinking_status


class ThinkingProcessor(BaseProcessor):
    """Displays and updates Claude's thinking status."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.msg_key: str | None = None
        self.last_update: float = 0.0
        self.last_text: str | None = None

    async def process(self, screen: str) -> None:
        # Check if feature enabled
        feat_enabled = (
            self.ctx.thread.feat_thinking_status
            if self.ctx.thread
            else self.ctx.project.feat_thinking_status
        )
        if not feat_enabled:
            return

        thinking_text = parse_thinking_status(screen)

        if thinking_text:
            now = asyncio.get_event_loop().time()
            # Throttle: update every 3 seconds
            if now - self.last_update >= 3.0:
                key = f"thinking:{self.ctx.chat_id}:{self.ctx.thread_id}"
                needs_resend = self.ctx.thread.thinking_needs_resend if self.ctx.thread else False

                if self.msg_key is None:
                    # First time — send new message
                    self.log_debug(f"thinking status SEND: {thinking_text[:50]}...")
                    await self.send_nowait(thinking_text, replace_key=key)
                    self.msg_key = key

                elif needs_resend:
                    # Watcher sent message — delete + send to keep at bottom
                    self.log_debug(f"thinking status RESEND: {thinking_text[:50]}...")
                    await self.delete_by_key(self.msg_key)
                    await self.send_nowait(thinking_text, replace_key=key)
                    if self.ctx.thread:
                        self.ctx.thread.thinking_needs_resend = False

                else:
                    # No new messages — just edit in place
                    self.log_debug(f"thinking status EDIT: {thinking_text[:50]}...")
                    await self.edit_by_key(thinking_text, key)

                self.last_update = now
                self.last_text = thinking_text

        elif self.msg_key:
            # Claude finished thinking — delete status message
            self.log_debug("thinking status DELETE")
            await self.delete_by_key(self.msg_key)
            self.msg_key = None
            self.last_text = None
            self.last_update = 0.0
```

**Step 2: Update processors/__init__.py**

```python
# src/codogram/claude/poller/processors/__init__.py
"""Poller processors - each handles one concern."""
from .compact import CompactProcessor
from .thinking import ThinkingProcessor

__all__ = ["CompactProcessor", "ThinkingProcessor"]
```

**Step 3: Commit**

```bash
git add src/codogram/claude/poller/processors/
git commit -m "refactor(poller): extract ThinkingProcessor"
```

---

### Task 4: Create SuggestionsProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/suggestions.py`
- Modify: `src/codogram/claude/poller/processors/__init__.py`

**Step 1: Create suggestions.py**

```python
# src/codogram/claude/poller/processors/suggestions.py
"""Input suggestions processor."""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from ..base import BaseProcessor
from ...screen import parse_input_suggestion, parse_thinking_status
from ....core.session_manager import project_manager

# Track last suggestion per thread to avoid duplicates
_last_suggestions: dict[str, str | None] = {}


class SuggestionsProcessor(BaseProcessor):
    """Shows input suggestions as ReplyKeyboard."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.msg_key: str | None = None

    async def process(self, screen: str) -> None:
        # Check if feature enabled (chat-wide, not per-thread)
        if not self.ctx.project.feat_suggestions:
            if self.msg_key:
                # Feature disabled but message exists — cleanup
                self.log_debug("suggestion DELETE (feature disabled)")
                await self.delete_by_key(self.msg_key)
                self.msg_key = None
                _last_suggestions[self._suggestion_key] = None
            return

        # Don't show suggestions while thinking
        thinking_text = parse_thinking_status(screen)
        if thinking_text:
            return

        suggestion = parse_input_suggestion(screen)

        if suggestion and suggestion != _last_suggestions.get(self._suggestion_key):
            # New suggestion — send 💡 with ReplyKeyboard
            self.log_debug(f"suggestion NEW: {suggestion[:50]}...")
            self.msg_key = f"suggestion:{self.ctx.chat_id}:{self.ctx.thread_id}"

            from ....telegram.queue import OutgoingBatch
            batch = OutgoingBatch(
                chat_id=self.ctx.chat_id,
                thread_id=self.ctx.thread_id,
                messages=[{"text": "💡"}],
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text=suggestion)]],
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
                replace_key=self.msg_key,
            )
            msg_ids = await self.ctx.queue.enqueue(batch)
            _last_suggestions[self._suggestion_key] = suggestion

            # Persist message ID for cleanup after restart
            if self.ctx.thread and msg_ids:
                self.ctx.thread.last_suggestion_msg_id = msg_ids[0]
                project_manager._save()

        elif not suggestion and _last_suggestions.get(self._suggestion_key):
            # Suggestion gone — delete 💡 message
            self.log_debug("suggestion DELETE")
            if self.msg_key:
                await self.delete_by_key(self.msg_key)
                self.msg_key = None
            # Clear persisted message ID
            if self.ctx.thread:
                self.ctx.thread.last_suggestion_msg_id = None
                project_manager._save()
            _last_suggestions[self._suggestion_key] = None

    @property
    def _suggestion_key(self) -> str:
        return f"{self.ctx.chat_id}:{self.ctx.thread_id}"
```

**Step 2: Update processors/__init__.py**

```python
# src/codogram/claude/poller/processors/__init__.py
"""Poller processors - each handles one concern."""
from .compact import CompactProcessor
from .thinking import ThinkingProcessor
from .suggestions import SuggestionsProcessor

__all__ = ["CompactProcessor", "ThinkingProcessor", "SuggestionsProcessor"]
```

**Step 3: Commit**

```bash
git add src/codogram/claude/poller/processors/
git commit -m "refactor(poller): extract SuggestionsProcessor"
```

---

### Task 5: Create StuckProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/stuck.py`
- Modify: `src/codogram/claude/poller/processors/__init__.py`

**Step 1: Create stuck.py**

```python
# src/codogram/claude/poller/processors/stuck.py
"""Stuck message detection processor."""
from ..base import BaseProcessor
from ...screen import extract_input_text, PASTED_PATTERN


class StuckProcessor(BaseProcessor):
    """Detects stuck messages and sends Enter to unstick."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.input_text: str | None = None
        self.seen_count: int = 0

    async def process(self, screen: str) -> None:
        input_text = extract_input_text(screen)

        if not input_text:
            self._reset()
            return

        # Get effective thread for last_sent_message
        effective_thread = self.ctx.thread if self.ctx.thread else self.ctx.project.threads.get(None)
        last_msg = effective_thread.last_sent_message if effective_thread else None

        # Compare first line only (input_text is single line, last_msg may be multiline)
        # Use startswith because tmux wraps long lines - input_text may be truncated
        first_line = last_msg.split('\n')[0] if last_msg else None
        is_potentially_stuck = (
            PASTED_PATTERN.match(input_text) is not None or
            (first_line is not None and first_line.startswith(input_text))
        )

        if not is_potentially_stuck:
            self._reset()
            return

        if input_text == self.input_text:
            self.seen_count += 1
        else:
            self.input_text = input_text
            self.seen_count = 1

        # Debounce: seen twice in a row = stuck, send Enter
        if self.seen_count >= 2:
            self.log_info(f"stuck message detected ({self.seen_count}x), sending Enter")
            self.ctx.tmux.send_key("Enter")
            self._reset()
            # Clear last_sent_message to prevent re-triggering
            if effective_thread:
                effective_thread.last_sent_message = None

    def _reset(self) -> None:
        self.input_text = None
        self.seen_count = 0
```

**Step 2: Update processors/__init__.py**

```python
# src/codogram/claude/poller/processors/__init__.py
"""Poller processors - each handles one concern."""
from .compact import CompactProcessor
from .thinking import ThinkingProcessor
from .suggestions import SuggestionsProcessor
from .stuck import StuckProcessor

__all__ = ["CompactProcessor", "ThinkingProcessor", "SuggestionsProcessor", "StuckProcessor"]
```

**Step 3: Commit**

```bash
git add src/codogram/claude/poller/processors/
git commit -m "refactor(poller): extract StuckProcessor"
```

---

### Task 6: Create PermissionProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/permissions.py`
- Modify: `src/codogram/claude/poller/processors/__init__.py`

**Step 1: Create permissions.py**

```python
# src/codogram/claude/poller/processors/permissions.py
"""Permission prompt processor with state machine."""
import asyncio
from enum import Enum

from ..base import BaseProcessor
from ...screen import parse_screen, PermissionPrompt
from ....telegram.queue import OutgoingBatch
from ....telegram.keyboards import permission_keyboard
from ....state import permission_messages
from ....auto_accept import try_auto_accept
from ....config import settings
from ....utils.truncate import truncate_body


class PermissionState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"


SEPARATOR_SOLID = "────────────"


class PermissionProcessor(BaseProcessor):
    """Handles permission prompts with debounce and state machine."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.state = PermissionState.IDLE
        self.debounce_start: float = 0.0
        self.last_options: list[str] | None = None
        self.last_body: str | None = None
        self.content_msg_ids: list[int] = []
        self.kb_msg_id: int | None = None

    async def process(self, screen: str) -> None:
        parsed = parse_screen(screen)
        is_permission = isinstance(parsed, PermissionPrompt)

        # Debug: log if prompt character detected but no permission parsed
        if "❯" in screen and not is_permission:
            self.log_debug(f"prompt found but no permission! parsed={type(parsed).__name__}")

        if self.state == PermissionState.IDLE:
            await self._handle_idle(parsed, is_permission)
        elif self.state == PermissionState.DEBOUNCING:
            await self._handle_debouncing(parsed, is_permission)
        elif self.state == PermissionState.SHOWING:
            await self._handle_showing(parsed, is_permission)

    async def _handle_idle(self, parsed, is_permission: bool) -> None:
        if is_permission:
            self.log_debug(f"IDLE->DEBOUNCING: detected permission, options={parsed.options}")
            self.log_debug(f"body={parsed.body[:100] if parsed.body else 'none'}...")
            self.state = PermissionState.DEBOUNCING
            self.debounce_start = asyncio.get_event_loop().time()
            self.last_options = parsed.options

    async def _handle_debouncing(self, parsed, is_permission: bool) -> None:
        if not is_permission:
            self.log_debug("DEBOUNCING->IDLE: permission disappeared")
            self.state = PermissionState.IDLE
            self.last_options = None
            return

        if parsed.options != self.last_options:
            self.debounce_start = asyncio.get_event_loop().time()
            self.last_options = parsed.options
            return

        elapsed = asyncio.get_event_loop().time() - self.debounce_start
        if elapsed < settings.permission_poller_debounce:
            return

        # Debounce complete - check auto-accept or show prompt
        auto_accept = self.ctx.thread.auto_accept if self.ctx.thread else self.ctx.project.auto_accept
        verbose = self.ctx.thread.verbose if self.ctx.thread else self.ctx.project.verbose

        self.log_debug(f"DEBOUNCING: auto_accept={auto_accept} prompt_type={parsed.prompt_type.value}")

        if auto_accept:
            accepted = await try_auto_accept(
                parsed.options, parsed.body, self.ctx.tmux,
                self.ctx.queue, self.ctx.chat_id, self.ctx.thread_id,
                self.ctx.context_name, prompt_type=parsed.prompt_type, verbose=verbose,
            )
            if accepted:
                self.log_info("DEBOUNCING->SHOWING: auto-accepted successfully")
                self.state = PermissionState.SHOWING
                self.last_body = parsed.body
                return
            else:
                self.log_info("DEBOUNCING: auto_accept returned False, falling through to manual")

        # Show prompt in Telegram
        await self._send_permission(parsed, verbose)

    async def _handle_showing(self, parsed, is_permission: bool) -> None:
        if not is_permission:
            self.log_debug("SHOWING->IDLE: permission gone, cleaning up")
            await self._cleanup_messages()
            self._reset_state()
            return

        if parsed.options != self.last_options or parsed.body != self.last_body:
            # Options/body changed - check auto-accept or resend
            auto_accept = self.ctx.thread.auto_accept if self.ctx.thread else self.ctx.project.auto_accept
            verbose = self.ctx.thread.verbose if self.ctx.thread else self.ctx.project.verbose

            self.log_debug(f"SHOWING: options/body changed! auto_accept={auto_accept}")

            if auto_accept:
                accepted = await try_auto_accept(
                    parsed.options, parsed.body, self.ctx.tmux,
                    self.ctx.queue, self.ctx.chat_id, self.ctx.thread_id,
                    self.ctx.context_name, prompt_type=parsed.prompt_type, verbose=verbose,
                )
                if accepted:
                    self.log_info("SHOWING: options/body changed, auto-accepted again")
                    self.last_options = parsed.options
                    self.last_body = parsed.body
                    return

            # Resend prompt
            self.log_debug("SHOWING: body/options changed, resending")
            await self._cleanup_messages()
            await self._send_permission(parsed, verbose)

    async def _send_permission(self, parsed: PermissionPrompt, verbose: bool) -> None:
        try:
            display_body = truncate_body(parsed.body, verbose=verbose)

            messages = []
            if display_body:
                body_text = SEPARATOR_SOLID + "\n" + display_body
                messages.append({"text": body_text, "parse_mode": "MarkdownV2"})

            options_text = "\n".join(parsed.options)
            messages.append({"text": options_text})
            messages.append({"text": "👆"})

            kb = permission_keyboard(parsed.options, self.ctx.tmux_name)
            batch = OutgoingBatch(
                chat_id=self.ctx.chat_id,
                thread_id=self.ctx.thread_id,
                messages=messages,
                reply_markup=kb,
            )
            msg_ids = await self.ctx.queue.enqueue(batch)

            self.kb_msg_id = msg_ids[-1] if msg_ids else None
            self.content_msg_ids = msg_ids[:-1] if len(msg_ids) > 1 else []
            if self.kb_msg_id:
                permission_messages[self.kb_msg_id] = self.content_msg_ids
                self.log_debug(f"saved permission_messages[{self.kb_msg_id}] = {self.content_msg_ids}")

            self.state = PermissionState.SHOWING
            self.last_body = parsed.body
            self.log_debug(f"SHOWING: sent {len(parsed.options)} options, kb_msg={self.kb_msg_id}")
        except Exception as e:
            self.log_warning(f"send error: {e}")
            self.state = PermissionState.IDLE

    async def _cleanup_messages(self) -> None:
        if self.kb_msg_id and self.kb_msg_id in permission_messages:
            for msg_id in permission_messages[self.kb_msg_id]:
                try:
                    await self.ctx.bot.delete_message(self.ctx.chat_id, msg_id)
                except Exception:
                    pass
            try:
                await self.ctx.bot.delete_message(self.ctx.chat_id, self.kb_msg_id)
            except Exception:
                pass
            permission_messages.pop(self.kb_msg_id, None)

    def _reset_state(self) -> None:
        self.state = PermissionState.IDLE
        self.last_options = None
        self.last_body = None
        self.content_msg_ids = []
        self.kb_msg_id = None
```

**Step 2: Update processors/__init__.py**

```python
# src/codogram/claude/poller/processors/__init__.py
"""Poller processors - each handles one concern."""
from .compact import CompactProcessor
from .thinking import ThinkingProcessor
from .suggestions import SuggestionsProcessor
from .stuck import StuckProcessor
from .permissions import PermissionProcessor

__all__ = [
    "CompactProcessor",
    "ThinkingProcessor",
    "SuggestionsProcessor",
    "StuckProcessor",
    "PermissionProcessor",
]
```

**Step 3: Commit**

```bash
git add src/codogram/claude/poller/processors/
git commit -m "refactor(poller): extract PermissionProcessor with state machine"
```

---

### Task 7: Create crash.py and main poller loop

**Files:**
- Create: `src/codogram/claude/poller/crash.py`
- Create: `src/codogram/claude/poller/poller.py`
- Modify: `src/codogram/claude/poller/__init__.py`

**Step 1: Create crash.py**

```python
# src/codogram/claude/poller/crash.py
"""Crash detection logic."""
from ..screen import is_claude_ready

CRASH_SIGNATURES = [
    "panicked at",
    "fatal runtime error",
    "core dumped",
    "SIGSEGV",
    "SIGABRT",
]

SHELL_PROMPTS = ["➜", "$ ", "# ", "❯ "]


def detect_crash(screen: str) -> str | None:
    """Detect if Claude has crashed. Returns crash reason or None.

    Only triggers if ALL conditions met:
    1. Claude UI NOT visible (is_claude_ready = False)
    2. Shell prompt visible (Claude exited to shell)
    3. Crash signature in LAST 15 lines (not scrollback)
    """
    if is_claude_ready(screen):
        return None

    lines = screen.split("\n")
    last_lines = "\n".join(lines[-15:])

    has_shell = any(p in last_lines for p in SHELL_PROMPTS)
    if not has_shell:
        return None

    for sig in CRASH_SIGNATURES:
        if sig in last_lines:
            return sig
    return None
```

**Step 2: Create poller.py (main loop)**

```python
# src/codogram/claude/poller/poller.py
"""Main poller loop - orchestrates all processors."""
import asyncio
from typing import TYPE_CHECKING

from aiogram import Bot

if TYPE_CHECKING:
    from ...telegram.queue import TelegramQueue

from .context import PollerContext
from .crash import detect_crash
from .processors import (
    CompactProcessor,
    ThinkingProcessor,
    SuggestionsProcessor,
    StuckProcessor,
    PermissionProcessor,
)
from ...core.session_manager import ProjectState, ThreadInfo, project_manager
from ...tmux.session import TmuxSession
from ...telegram.queue import OutgoingBatch
from ...logging_config import logger
from ...config import settings
from ... import strings


async def create_poller_task(
    bot: Bot, project: ProjectState, telegram_queue: "TelegramQueue"
) -> asyncio.Task:
    """Create permission poller task for project (no thread)."""
    return asyncio.create_task(permission_poller(bot, project, telegram_queue, thread=None))


async def create_poller_task_for_thread(
    bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue"
) -> asyncio.Task:
    """Create permission poller task for a specific thread."""
    return asyncio.create_task(permission_poller(bot, project, telegram_queue, thread=thread))


async def permission_poller(
    bot: Bot,
    project: ProjectState,
    telegram_queue: "TelegramQueue",
    thread: ThreadInfo | None = None,
) -> None:
    """Background poller for permission prompts and status updates.

    Polls tmux every interval, delegates to processors.
    """
    # Build context
    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        thread_id = thread.thread_id
        log_prefix = f"Thread poller [{thread.name}]"
        context_name = thread.name
    else:
        tmux_name = project.tmux_session
        thread_id = None
        log_prefix = "Poller"
        context_name = project.project_name

    logger.info(f"{log_prefix}: started for {context_name} (tmux: {tmux_name})")

    tmux = TmuxSession(tmux_name, project.cwd)

    ctx = PollerContext(
        bot=bot,
        project=project,
        thread=thread,
        tmux=tmux,
        queue=telegram_queue,
        chat_id=project.chat_id,
        thread_id=thread_id,
        log_prefix=log_prefix,
        context_name=context_name,
        tmux_name=tmux_name,
    )

    # Cleanup old suggestion message from previous session
    if thread and thread.last_suggestion_msg_id:
        try:
            await bot.delete_message(project.chat_id, thread.last_suggestion_msg_id)
            logger.info(f"{log_prefix}: cleaned up old suggestion msg {thread.last_suggestion_msg_id}")
        except Exception as e:
            logger.debug(f"{log_prefix}: failed to cleanup old suggestion: {e}")
        thread.last_suggestion_msg_id = None
        project_manager._save()

    # Initialize processors
    processors = [
        CompactProcessor(ctx),
        ThinkingProcessor(ctx),
        SuggestionsProcessor(ctx),
        StuckProcessor(ctx),
        PermissionProcessor(ctx),
    ]

    poll_interval = settings.permission_poller_interval

    # Main loop
    while True:
        await asyncio.sleep(poll_interval)

        try:
            screen = tmux.capture_pane()
        except Exception as e:
            logger.warning(f"{log_prefix}: capture error: {e}")
            continue

        # Crash detection (exits poller)
        crash_reason = detect_crash(screen)
        if crash_reason:
            logger.error(f"{log_prefix}: Claude crashed! Reason: {crash_reason}")
            try:
                batch = OutgoingBatch(
                    chat_id=project.chat_id,
                    thread_id=thread_id,
                    messages=[{"text": strings.CLAUDE_CRASHED.format(reason=crash_reason), "parse_mode": "MarkdownV2"}],
                )
                await telegram_queue.enqueue_nowait(batch)
            except Exception:
                pass
            return

        # Process all processors
        for processor in processors:
            try:
                await processor.process(screen)
            except Exception as e:
                logger.warning(f"{log_prefix}: {processor.__class__.__name__} error: {e}")
```

**Step 3: Update poller/__init__.py**

```python
# src/codogram/claude/poller/__init__.py
"""Poller package - background permission and status polling."""
from .context import PollerContext
from .base import BaseProcessor
from .poller import permission_poller, create_poller_task, create_poller_task_for_thread

__all__ = [
    "PollerContext",
    "BaseProcessor",
    "permission_poller",
    "create_poller_task",
    "create_poller_task_for_thread",
]
```

**Step 4: Commit**

```bash
git add src/codogram/claude/poller/
git commit -m "refactor(poller): create main loop with all processors"
```

---

### Task 8: Update imports and delete old poller.py

**Files:**
- Modify: `src/codogram/claude/__init__.py`
- Delete: `src/codogram/claude/poller.py` (old monolithic file)

**Step 1: Update claude/__init__.py**

```python
# src/codogram/claude/__init__.py
"""Claude CLI integration - screen parsing, history watching, polling."""
from .poller import create_poller_task, create_poller_task_for_thread, permission_poller

__all__ = [
    "create_poller_task",
    "create_poller_task_for_thread",
    "permission_poller",
]
```

**Step 2: Find and update all imports**

Run grep to find all imports of old poller:
```bash
grep -r "from.*claude.*poller import\|from.*claude\.poller import" src/
```

Update each file to import from `claude.poller` (package) instead of `claude.poller` (module).

Most likely files:
- `src/codogram/core/coordinator.py`

**Step 3: Delete old poller.py**

```bash
rm src/codogram/claude/poller.py
```

Wait, the old file IS at `src/codogram/claude/poller.py` which will conflict with the new package `src/codogram/claude/poller/`. We need to:
1. First rename/backup old file
2. Create new package
3. Then delete old file

Actually, since we already created the poller/ directory, the old poller.py should have been handled. Let me adjust:

**Step 3 (corrected): Verify old poller.py is removed**

The old `src/codogram/claude/poller.py` should be deleted since we created `src/codogram/claude/poller/` directory.

```bash
# If old file still exists, remove it
rm -f src/codogram/claude/poller.py
```

**Step 4: Test imports**

```bash
cd /home/superbereza/dev/codogram/.worktrees/askuserquestion-support
python -c "from codogram.claude.poller import create_poller_task, create_poller_task_for_thread; print('OK')"
```

Expected: `OK`

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(poller): update imports, delete old monolithic poller.py"
```

---

## Phase 2: AskUserQuestion Support

### Task 9: Add AskUserQuestion detection to screen.py

**Files:**
- Modify: `src/codogram/claude/screen.py`

**Step 1: Add AskUserQuestion dataclass**

Add after `PermissionPrompt` class:

```python
@dataclass
class AskUserQuestion:
    """Parsed AskUserQuestion prompt from Claude screen."""
    question: str              # "Сколько мониторов?"
    header: str                # "Мониторы"
    options: list[str]         # ["1. 1", "2. 2", "3. 3+", "4. Type something."]
    descriptions: dict[str, str]  # {"1": "Минимализм", "2": "Код + доки", ...}
```

**Step 2: Add detection function**

Add before `parse_screen`:

```python
def _parse_ask_user_question(lines: list[str]) -> AskUserQuestion | None:
    """Parse AskUserQuestion prompt (two separators + checkboxes).

    Format:
    ────────────────────────────────────────────
     ☐ Header  (or ☒ for completed)

    Question text?

    ❯ 1. Option1
         Description1
      2. Option2
         Description2
    ────────────────────────────────────────────
      Chat about this

    Returns AskUserQuestion or None if not an AskUserQuestion prompt.
    """
    # Find all separator indices
    sep_indices = []
    for i, line in enumerate(lines):
        if "─" * SCREEN_SEPARATOR_MIN_DASHES in line:
            sep_indices.append(i)

    # Need at least 2 separators
    if len(sep_indices) < 2:
        return None

    # Get content between first two separators (from end, to handle scrollback)
    # Use the last two separators
    start_sep = sep_indices[-2]
    end_sep = sep_indices[-1]

    content_lines = lines[start_sep + 1:end_sep]

    # Must have checkbox markers (☐ or ☒) - unique to AskUserQuestion
    content_text = "\n".join(content_lines)
    if "☐" not in content_text and "☒" not in content_text:
        return None

    # Parse header from line with ☐/☒
    header = ""
    header_line_idx = -1
    for i, line in enumerate(content_lines):
        if "☐" in line or "☒" in line:
            # Extract header: " ☐ Header" -> "Header"
            # May have multiple checkboxes: "← ☐ A ☐ B ☒ C ✔ Submit →"
            # Find the unchecked one (☐) - that's current question
            match = re.search(r'☐\s+(\w+)', line)
            if match:
                header = match.group(1)
            header_line_idx = i
            break

    if not header:
        return None

    # Parse question - first non-empty line after header line
    question = ""
    question_line_idx = -1
    for i in range(header_line_idx + 1, len(content_lines)):
        line = content_lines[i].strip()
        if line and not line.startswith("❯") and not re.match(r'\d+\.', line):
            question = line
            question_line_idx = i
            break

    # Parse options and descriptions
    options = []
    descriptions = {}
    current_option_num = None

    for i in range(question_line_idx + 1 if question_line_idx >= 0 else header_line_idx + 1, len(content_lines)):
        line = content_lines[i]
        stripped = line.strip()

        # Option line: "❯ 1. Text" or "  2. Text"
        opt_match = re.match(r'[❯\s]*(\d+)\.\s+(.+)', stripped)
        if opt_match:
            num = opt_match.group(1)
            text = opt_match.group(2)
            options.append(f"{num}. {text}")
            current_option_num = num
        elif current_option_num and stripped and not stripped.startswith(("Enter", "↑", "Tab", "Esc", "Chat")):
            # Description line (indented, after option)
            # Only if it looks like a description (not UI hints)
            descriptions[current_option_num] = stripped

    if not options:
        return None

    return AskUserQuestion(
        question=question,
        header=header,
        options=options,
        descriptions=descriptions,
    )
```

**Step 3: Update parse_screen to check AskUserQuestion**

Modify `parse_screen` function, add check after MCP trust and before permission:

```python
def parse_screen(output: str) -> ScreenState:
    """Parse tmux capture-pane output to detect state.

    Parsing order (most specific first):
    1. MCP trust prompt (box-style) — ╭╮╯╰│ characters
    2. AskUserQuestion — two ──── separators + ☐/☒ checkboxes
    3. Regular permission prompt — ──── separator + ❯ options
    4. Permission without separator — ❯ options only (trust folder)
    5. Tool progress — ● or ✶ markers
    6. Idle — default
    """
    lines = output.split("\n")

    # 1. Try MCP trust prompt first (most specific)
    mcp_result = _parse_mcp_trust_prompt(lines)
    if mcp_result:
        return mcp_result

    # 2. Try AskUserQuestion (two separators + checkboxes)
    ask_result = _parse_ask_user_question(lines)
    if ask_result:
        return ask_result

    # ... rest of existing code unchanged ...
```

**Step 4: Update ScreenState type alias**

```python
ScreenState = PermissionPrompt | AskUserQuestion | ToolProgress | Idle
```

**Step 5: Commit**

```bash
git add src/codogram/claude/screen.py
git commit -m "feat(screen): add AskUserQuestion detection"
```

---

### Task 10: Create AskUserQuestionProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/ask_user.py`
- Modify: `src/codogram/claude/poller/processors/__init__.py`
- Modify: `src/codogram/claude/poller/poller.py`

**Step 1: Create ask_user.py**

```python
# src/codogram/claude/poller/processors/ask_user.py
"""AskUserQuestion prompt processor."""
import asyncio
from enum import Enum

from ..base import BaseProcessor
from ...screen import parse_screen, AskUserQuestion
from ....telegram.queue import OutgoingBatch
from ....telegram.keyboards import ask_user_keyboard
from ....state import permission_messages
from ....config import settings


class AskUserState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"


SEPARATOR_SOLID = "────────────"


class AskUserQuestionProcessor(BaseProcessor):
    """Handles AskUserQuestion prompts with debounce and state machine."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.state = AskUserState.IDLE
        self.debounce_start: float = 0.0
        self.last_options: list[str] | None = None
        self.last_question: str | None = None
        self.content_msg_ids: list[int] = []
        self.kb_msg_id: int | None = None

    async def process(self, screen: str) -> None:
        parsed = parse_screen(screen)
        is_ask_user = isinstance(parsed, AskUserQuestion)

        if self.state == AskUserState.IDLE:
            await self._handle_idle(parsed, is_ask_user)
        elif self.state == AskUserState.DEBOUNCING:
            await self._handle_debouncing(parsed, is_ask_user)
        elif self.state == AskUserState.SHOWING:
            await self._handle_showing(parsed, is_ask_user)

    async def _handle_idle(self, parsed, is_ask_user: bool) -> None:
        if is_ask_user:
            self.log_debug(f"IDLE->DEBOUNCING: detected AskUserQuestion, header={parsed.header}")
            self.state = AskUserState.DEBOUNCING
            self.debounce_start = asyncio.get_event_loop().time()
            self.last_options = parsed.options

    async def _handle_debouncing(self, parsed, is_ask_user: bool) -> None:
        if not is_ask_user:
            self.log_debug("DEBOUNCING->IDLE: AskUserQuestion disappeared")
            self.state = AskUserState.IDLE
            self.last_options = None
            return

        if parsed.options != self.last_options:
            self.debounce_start = asyncio.get_event_loop().time()
            self.last_options = parsed.options
            return

        elapsed = asyncio.get_event_loop().time() - self.debounce_start
        if elapsed < settings.permission_poller_debounce:
            return

        # Debounce complete - show prompt
        await self._send_ask_user(parsed)

    async def _handle_showing(self, parsed, is_ask_user: bool) -> None:
        if not is_ask_user:
            self.log_debug("SHOWING->IDLE: AskUserQuestion gone, cleaning up")
            await self._cleanup_messages()
            self._reset_state()
            return

        if parsed.options != self.last_options or parsed.question != self.last_question:
            # Options/question changed - resend
            self.log_debug("SHOWING: options/question changed, resending")
            await self._cleanup_messages()
            await self._send_ask_user(parsed)

    async def _send_ask_user(self, parsed: AskUserQuestion) -> None:
        try:
            # Build message content
            # Format: header + question + options with descriptions
            lines = [SEPARATOR_SOLID]
            lines.append(f"☐ {parsed.header}")
            lines.append("")
            lines.append(parsed.question)
            lines.append("")

            for opt in parsed.options:
                num = opt.split(".")[0]
                desc = parsed.descriptions.get(num, "")
                if desc:
                    lines.append(f"{opt} — {desc}")
                else:
                    lines.append(opt)

            body_text = "\n".join(lines)

            messages = [
                {"text": body_text},
                {"text": "👆"},
            ]

            kb = ask_user_keyboard(parsed.options, self.ctx.tmux_name)
            batch = OutgoingBatch(
                chat_id=self.ctx.chat_id,
                thread_id=self.ctx.thread_id,
                messages=messages,
                reply_markup=kb,
            )
            msg_ids = await self.ctx.queue.enqueue(batch)

            self.kb_msg_id = msg_ids[-1] if msg_ids else None
            self.content_msg_ids = msg_ids[:-1] if len(msg_ids) > 1 else []
            if self.kb_msg_id:
                permission_messages[self.kb_msg_id] = self.content_msg_ids

            self.state = AskUserState.SHOWING
            self.last_question = parsed.question
            self.log_debug(f"SHOWING: sent AskUserQuestion, kb_msg={self.kb_msg_id}")
        except Exception as e:
            self.log_warning(f"send error: {e}")
            self.state = AskUserState.IDLE

    async def _cleanup_messages(self) -> None:
        if self.kb_msg_id and self.kb_msg_id in permission_messages:
            for msg_id in permission_messages[self.kb_msg_id]:
                try:
                    await self.ctx.bot.delete_message(self.ctx.chat_id, msg_id)
                except Exception:
                    pass
            try:
                await self.ctx.bot.delete_message(self.ctx.chat_id, self.kb_msg_id)
            except Exception:
                pass
            permission_messages.pop(self.kb_msg_id, None)

    def _reset_state(self) -> None:
        self.state = AskUserState.IDLE
        self.last_options = None
        self.last_question = None
        self.content_msg_ids = []
        self.kb_msg_id = None
```

**Step 2: Update processors/__init__.py**

```python
# src/codogram/claude/poller/processors/__init__.py
"""Poller processors - each handles one concern."""
from .compact import CompactProcessor
from .thinking import ThinkingProcessor
from .suggestions import SuggestionsProcessor
from .stuck import StuckProcessor
from .permissions import PermissionProcessor
from .ask_user import AskUserQuestionProcessor

__all__ = [
    "CompactProcessor",
    "ThinkingProcessor",
    "SuggestionsProcessor",
    "StuckProcessor",
    "PermissionProcessor",
    "AskUserQuestionProcessor",
]
```

**Step 3: Update poller.py to include AskUserQuestionProcessor**

In `poller.py`, update the processors list:

```python
from .processors import (
    CompactProcessor,
    ThinkingProcessor,
    SuggestionsProcessor,
    StuckProcessor,
    PermissionProcessor,
    AskUserQuestionProcessor,
)

# In permission_poller function:
processors = [
    CompactProcessor(ctx),
    ThinkingProcessor(ctx),
    SuggestionsProcessor(ctx),
    StuckProcessor(ctx),
    PermissionProcessor(ctx),
    AskUserQuestionProcessor(ctx),
]
```

**Step 4: Commit**

```bash
git add src/codogram/claude/poller/
git commit -m "feat(poller): add AskUserQuestionProcessor"
```

---

### Task 11: Create ask_user_keyboard

**Files:**
- Create: `src/codogram/telegram/keyboards/ask_user.py`
- Modify: `src/codogram/telegram/keyboards/__init__.py`

**Step 1: Create ask_user.py**

```python
# src/codogram/telegram/keyboards/ask_user.py
"""Inline keyboard for AskUserQuestion prompts."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ... import strings


def ask_user_keyboard(options: list[str], tmux_session: str) -> InlineKeyboardMarkup:
    """Build inline keyboard from AskUserQuestion options.

    Args:
        options: List of options in format ["1. Option", "2. Option", ...]
        tmux_session: Tmux session name for stable routing

    Returns:
        InlineKeyboardMarkup with buttons for each option plus Cancel
    """
    buttons = []

    for opt in options[:4]:  # Max 4 options
        # Extract number from "1. Option" -> "1"
        num = opt.split(".")[0].strip()
        label = opt.split(".", 1)[1].strip()[:20]  # Truncate label

        # "Type something" -> "Другое"
        if "type something" in label.lower():
            label = "Другое"

        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"ask:{num}:{tmux_session}"
        )])

    # Always add Esc button
    buttons.append([InlineKeyboardButton(
        text=strings.BTN_CANCEL_X,
        callback_data=f"ask:esc:{tmux_session}"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

**Step 2: Update keyboards/__init__.py**

```python
# src/codogram/telegram/keyboards/__init__.py
"""Keyboard builders for Telegram bot."""
from .permissions import permission_keyboard
from .ask_user import ask_user_keyboard
from .settings import settings_keyboard
# ... other imports ...

__all__ = [
    "permission_keyboard",
    "ask_user_keyboard",
    "settings_keyboard",
    # ... other exports ...
]
```

**Step 3: Commit**

```bash
git add src/codogram/telegram/keyboards/
git commit -m "feat(keyboards): add ask_user_keyboard"
```

---

### Task 12: Create AskUserQuestion callback handler

**Files:**
- Create: `src/codogram/handlers/ask_user.py`
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Create ask_user.py handler**

```python
# src/codogram/handlers/ask_user.py
"""AskUserQuestion callback handlers."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from ..core.session_manager import project_manager
from ..tmux.session import TmuxSession
from ..state import permission_messages
from ..logging_config import logger

router = Router(name="ask_user")


@router.callback_query(F.data.startswith("ask:"))
async def on_ask_user_callback(callback: CallbackQuery):
    """Handle AskUserQuestion button press.

    Note: Admin check done by global AdminMiddleware on dp level.
    """
    logger.info(f"ask_user_callback: data={callback.data} from user={callback.from_user.id}")

    # Parse callback data: ask:{action}:{tmux_session}
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        logger.warning(f"ask_user_callback: invalid format data={callback.data}")
        await callback.answer("Invalid callback format")
        return

    action = parts[1]
    tmux_session = parts[2]
    logger.debug(f"ask_user_callback: action={action} tmux={tmux_session}")

    # Find project
    project = project_manager.get_by_tmux(tmux_session)
    if not project:
        logger.warning(f"ask_user_callback: project not found for tmux={tmux_session}")
        await callback.answer("Session not found")
        return

    if not project.cwd:
        logger.warning(f"ask_user_callback: project has no cwd tmux={tmux_session}")
        await callback.answer("Project has no cwd")
        return

    # Check tmux exists
    tmux = TmuxSession(tmux_session, project.cwd)
    if not tmux.exists():
        logger.warning(f"ask_user_callback: tmux session closed tmux={tmux_session}")
        await callback.answer("Tmux session closed")
        return

    # Cleanup messages
    await _cleanup_messages(callback)

    # Send key to tmux
    if action == "esc":
        logger.info(f"ask_user_callback: sending Escape to tmux={tmux_session}")
        tmux.send_key("Escape")
    else:
        logger.info(f"ask_user_callback: sending {action} to tmux={tmux_session}")
        tmux.send_key(action)

    await callback.answer()


async def _cleanup_messages(callback: CallbackQuery):
    """Delete content messages and keyboard."""
    chat_id = callback.message.chat.id
    kb_msg_id = callback.message.message_id

    content_ids = permission_messages.pop(kb_msg_id, [])
    for msg_id in content_ids:
        try:
            await callback.bot.delete_message(chat_id, msg_id)
        except Exception as e:
            logger.warning(f"cleanup: failed to delete content msg {msg_id}: {e}")

    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"cleanup: failed to delete keyboard msg {kb_msg_id}: {e}")
```

**Step 2: Update handlers/__init__.py**

Add to the router registration:

```python
from .ask_user import router as ask_user_router

# In register_handlers or wherever routers are included:
dp.include_router(ask_user_router)
```

Check `src/codogram/handlers/__init__.py` for exact pattern used.

**Step 3: Commit**

```bash
git add src/codogram/handlers/
git commit -m "feat(handlers): add AskUserQuestion callback handler"
```

---

### Task 13: Hide AskUserQuestion from watcher

**Files:**
- Modify: `src/codogram/claude/history_watcher.py`

**Step 1: Update _entry_to_messages**

In `_entry_to_messages` function, add check to hide AskUserQuestion:

```python
def _entry_to_messages(entry: ParsedEntry, verbose: bool = False) -> list[dict]:
    """Convert ParsedEntry to list of message dicts for queue."""
    messages = []

    if entry.content_type == ContentType.TEXT:
        messages.append({"text": f"● {entry.text}", "parse_mode": "MarkdownV2"})

    elif entry.content_type == ContentType.TOOL_USE:
        # Hide AskUserQuestion - shown by poller instead
        if entry.tool_name == "AskUserQuestion":
            return []

        text = format_tool_use(entry.tool_name, entry.tool_input, verbose=verbose)
        messages.append({"text": text, "parse_mode": "MarkdownV2"})

    return messages
```

**Step 2: Commit**

```bash
git add src/codogram/claude/history_watcher.py
git commit -m "feat(watcher): hide AskUserQuestion tool_use from Telegram"
```

---

## Phase 3: Testing

### Task 14: Manual E2E testing

**Step 1: Start bot from worktree**

```bash
./kill-instance-and-start-from-worktree.sh
```

**Step 2: Trigger AskUserQuestion in tmux**

In `claude-codogram-debug`:
```
запусти AskUserQuestion с одним вопросом
```

**Step 3: Verify in Telegram**

Check that:
- AskUserQuestion appears with buttons
- Clicking option sends number to tmux
- Messages are cleaned up after selection

**Step 4: Test "Type something" flow**

Navigate to "Type something" option, verify button works.

**Step 5: Test permission prompts still work**

Run a command that needs permission, verify existing flow unchanged.

---

### Task 15: Final commit and cleanup

**Step 1: Verify no regressions**

```bash
# Run bot and test manually
./kill-instance-and-start-from-worktree.sh

# Check logs
tail -f logs/codogram.log
```

**Step 2: Final commit if needed**

```bash
git status
# If any uncommitted changes:
git add -A
git commit -m "chore: cleanup after AskUserQuestion implementation"
```

**Step 3: Restore main bot**

```bash
cd /home/superbereza/dev/codogram
./stop-and-restart.sh
```
