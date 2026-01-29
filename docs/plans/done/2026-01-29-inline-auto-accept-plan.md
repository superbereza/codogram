# Inline Auto-Accept Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Edit last tool message to add auto-accept suffix instead of sending separate notification.

**Architecture:** Use `replace_key` pattern from TelegramQueue to track last tool message. Store original text in ThreadInfo. Edit message on auto-accept, fallback to new message on failure.

**Tech Stack:** Python, aiogram, TelegramQueue

---

## Task 1: Add runtime fields to ThreadInfo

**Files:**
- Modify: `src/codogram/core/session_manager.py:178-180`

**Step 1: Add fields after `thinking_needs_resend`**

```python
    # Runtime-only (not persisted):
    notified_closed: bool = False      # True = already sent "session closed" notification
    thinking_needs_resend: bool = False  # True = watcher sent message, thinking needs delete+send

    # For inline auto-accept:
    last_tool_msg_text: str | None = None  # Original text for edit
    auto_accept_count: int = 0             # Counter for hint frequency
```

**Step 2: Verify no persistence needed**

Check `_thread_to_dict()` and `_dict_to_thread()` in same file - these fields should NOT be in the serialization list (runtime-only).

**Step 3: Commit**

```bash
git add src/codogram/core/session_manager.py
git commit -m "feat: add runtime fields for inline auto-accept"
```

---

## Task 2: Add strings constants

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Add constants after line ~23 (after SNIP)**

```python
# --- Auto-accept ---

AUTO_ACCEPT_SUFFIX = "\n\nUPD: 🤖 auto accepted"
AUTO_ACCEPT_HINT = " (/auto_accept to disable)"
```

**Step 2: Commit**

```bash
git add src/codogram/strings.py
git commit -m "feat: add auto-accept inline notification strings"
```

---

## Task 3: Add replace_key to tool messages in history_watcher

**Files:**
- Modify: `src/codogram/claude/history_watcher.py:355-365`

**Step 1: Build replace_key for tool messages**

In `watch_thread_jsonl()`, find where `OutgoingBatch` is created for tool messages (around line 357). Change to:

```python
                else:
                    # Normal mode or non-tool content - send as usual
                    # Use replace_key for tool messages to enable inline auto-accept edit
                    replace_key = None
                    if entry.content_type == ContentType.TOOL_USE:
                        replace_key = f"tool:{project.chat_id}:{thread.thread_id}"
                        # Save original text for later edit
                        thread.last_tool_msg_text = messages[0].get("text")

                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread.thread_id,
                        messages=messages,
                        replace_key=replace_key,
                    )
                    telegram_ids = await telegram_queue.enqueue(batch)
                    logger.info(f"message_sent: msg_id={msg_id:06x} thread={thread.name} telegram_ids={telegram_ids}")

                    # Reset current mode state on TEXT content (Claude's response)
                    # This starts fresh for the next sequence of tool calls
                    if entry.content_type == ContentType.TEXT:
                        current_mode_active = False
                        thread.last_tool_msg_text = None  # Reset on text response
```

**Step 2: Commit**

```bash
git add src/codogram/claude/history_watcher.py
git commit -m "feat: add replace_key to tool messages for inline auto-accept"
```

---

## Task 4: Refactor try_auto_accept signature

**Files:**
- Modify: `src/codogram/auto_accept.py:52-63`
- Modify: `src/codogram/claude/poller/processors/permissions.py:112-117, 146-151`

**Step 1: Change signature in auto_accept.py**

Before:
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
    display_mode: str = "lines",
    line_limit: int = 5,
) -> bool:
```

After:
```python
async def try_auto_accept(
    options: list[str],
    body: str | None,
    tmux: TmuxSession,
    telegram_queue: "TelegramQueue",
    chat_id: int,
    context_name: str,
    prompt_type: PromptType = PromptType.REGULAR,
    thread: "ThreadInfo | None" = None,
) -> bool:
```

**Step 2: Add import and extract settings inside function**

```python
from .core.session_manager import ThreadInfo, get_thread_setting
from .config import get_global_defaults
```

At start of function:
```python
    # Extract settings from thread
    global_defaults = get_global_defaults()
    thread_id = thread.thread_id if thread else None
    display_mode = get_thread_setting(thread, "display_mode", global_defaults) if thread else "lines"
    line_limit = get_thread_setting(thread, "line_limit", global_defaults) if thread else 5
```

**Step 3: Update callers in permissions.py**

Find both calls (lines ~112-117 and ~146-151) and change:

Before:
```python
accepted = await try_auto_accept(
    parsed.options, parsed.body, self.ctx.tmux,
    self.ctx.queue, self.ctx.chat_id, self.ctx.thread_id,
    self.ctx.context_name, prompt_type=parsed.prompt_type,
    display_mode=display_mode, line_limit=line_limit,
)
```

After:
```python
accepted = await try_auto_accept(
    parsed.options, parsed.body, self.ctx.tmux,
    self.ctx.queue, self.ctx.chat_id,
    self.ctx.context_name, prompt_type=parsed.prompt_type,
    thread=self.ctx.thread,
)
```

**Step 4: Remove unused imports from permissions.py**

Remove `line_limit` variable since it's no longer needed at call site (but keep `display_mode` if used elsewhere).

**Step 5: Run tests**

```bash
pytest tests/ -v -k "auto_accept or permission" --tb=short
```

**Step 6: Commit**

```bash
git add src/codogram/auto_accept.py src/codogram/claude/poller/processors/permissions.py
git commit -m "refactor: pass thread to try_auto_accept instead of individual settings"
```

---

## Task 5: Implement inline edit logic in try_auto_accept

**Files:**
- Modify: `src/codogram/auto_accept.py`

**Step 1: Add EditBatch import**

```python
from .telegram.queue import OutgoingBatch, EditBatch
```

**Step 2: Add strings import**

```python
from . import strings
```

**Step 3: Replace notification sending logic (lines ~92-113)**

Replace the existing notification block with:

```python
    # Send notification based on display_mode
    if display_mode in ("silence", "current"):
        # No notification in silence/current mode
        pass
    else:
        # Try to edit last tool message (inline auto-accept)
        edited = False
        if thread and thread.last_tool_msg_text:
            replace_key = f"tool:{chat_id}:{thread.thread_id}"

            # Build suffix with optional hint
            thread.auto_accept_count += 1
            suffix = strings.AUTO_ACCEPT_SUFFIX
            if thread.auto_accept_count % 10 == 0:
                suffix += strings.AUTO_ACCEPT_HINT

            new_text = thread.last_tool_msg_text + suffix

            # Check length limit (Telegram max 4096)
            if len(new_text) <= 4096:
                try:
                    batch = EditBatch(
                        chat_id=chat_id,
                        message_id=0,  # Lookup from sent_statuses via replace_key
                        text=new_text,
                        parse_mode="MarkdownV2",
                        replace_key=replace_key,
                    )
                    await telegram_queue.enqueue(batch)
                    # Update stored text for potential next edit
                    thread.last_tool_msg_text = new_text
                    edited = True
                    logger.debug(f"try_auto_accept: edited tool message with suffix")
                except Exception as e:
                    logger.debug(f"try_auto_accept: edit failed, falling back: {e}")

        # Fallback: send new message if edit failed
        if not edited:
            # Build body text based on display_mode
            if display_mode == "headers":
                body_text = body.split("\n")[0][:60] if body else "[no details]"
            elif display_mode == "show_all":
                body_text = body if body else "[no details]"
            else:
                body_text = truncate_body(body, verbose=False, max_lines=line_limit) if body else "[no details]"

            batch = OutgoingBatch(
                chat_id=chat_id,
                thread_id=thread.thread_id if thread else None,
                messages=[{"text": f"🤖 Auto: {body_text}", "parse_mode": "MarkdownV2"}],
            )
            await telegram_queue.enqueue_nowait(batch)
```

**Step 4: Run tests**

```bash
pytest tests/ -v -k "auto_accept" --tb=short
```

**Step 5: Commit**

```bash
git add src/codogram/auto_accept.py
git commit -m "feat: implement inline auto-accept edit with fallback"
```

---

## Task 6: Manual E2E test

**Files:**
- None (manual testing)

**Step 1: Start bot from worktree**

```bash
./kill-instance-and-start-from-worktree.sh
```

**Step 2: Enable auto_accept in test chat**

Send `/auto_accept` in a project chat to enable.

**Step 3: Trigger multiple tool calls**

Send a message that causes Claude to use tools (e.g., "read file X").

**Step 4: Verify behavior**

- First tool message appears normally
- Auto-accept adds "UPD: 🤖 auto accepted" suffix to the SAME message (not new message)
- Every 10th shows hint with "/auto_accept to disable"

**Step 5: Test fallback**

- Delete the tool message manually while Claude is working
- Next auto-accept should send new message (fallback)

**Step 6: Test silence mode**

- Set `/verbose` to silence mode
- Auto-accept should show nothing

---

## Task 7: Final commit and merge prep

**Step 1: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

**Step 2: Review changes**

```bash
git diff main --stat
```

**Step 3: Create summary commit if needed**

If all individual commits are clean, no action needed. Otherwise squash or amend.
