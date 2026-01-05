# Telegramify-Markdown Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace manual underscore escaping with full GFM → MarkdownV2 conversion using telegramify-markdown library.

**Architecture:** All messages go through `telegram_queue.py:_send_batch()`. Apply `markdownify()` there before sending. Change all `parse_mode="Markdown"` to `parse_mode="MarkdownV2"`. Update our `*bold*` to `**bold**` (GFM syntax).

**Tech Stack:** Python 3.10+, aiogram 3.x, telegramify-markdown 0.5+

---

## Task 1: Add dependency

**Files:**
- Modify: `pyproject.toml:5-9`

**Step 1: Add telegramify-markdown to dependencies**

```toml
dependencies = [
    "aiogram>=3.4",
    "aiofiles>=23.0",
    "pydantic-settings>=2.0",
    "telegramify-markdown>=0.5",
]
```

**Step 2: Install dependency**

Run: `pip install telegramify-markdown`
Expected: Successfully installed telegramify-markdown-0.5.4

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add telegramify-markdown for GFM conversion"
```

---

## Task 2: Update telegram_queue.py - replace escape function

**Files:**
- Modify: `src/codogram/telegram_queue.py:1-50`

**Step 1: Replace imports and remove old function**

Remove lines 4, 16-40 (import re, regex constants, escape_markdown_underscores function).

Add import:
```python
import telegramify_markdown
```

**Step 2: Update _send_batch to use markdownify**

In `_send_batch()`, replace the escape call (lines 214-216):

```python
# Was:
if msg.get("parse_mode") == "Markdown":
    msg["text"] = escape_markdown_underscores(msg.get("text", ""))

# Becomes:
if msg.get("parse_mode") == "MarkdownV2":
    try:
        msg["text"] = telegramify_markdown.markdownify(
            msg.get("text", ""),
            max_line_length=None,
            normalize_whitespace=False
        )
    except Exception as e:
        from .logging_config import logger
        logger.warning(f"markdownify failed: {e}")
```

**Step 3: Verify syntax**

Run: `python -m py_compile src/codogram/telegram_queue.py`
Expected: No output (success)

**Step 4: Commit**

```bash
git add src/codogram/telegram_queue.py
git commit -m "refactor(queue): replace escape with telegramify-markdown"
```

---

## Task 3: Update watcher.py - fix bold syntax

**Files:**
- Modify: `src/codogram/watcher.py:110-134`

**Step 1: Replace *Bold* with **Bold** in format_tool_use**

```python
# Line 110-111:
if desc:
    return f"● **Bash**: {desc}\n`{cmd}`"
return f"● **Bash**\n`{cmd}`"

# Line 114:
return f"● **Read** `{path}`"

# Line 117:
return f"● **Write** `{path}`"

# Line 120:
return f"● **Edit** `{path}`"

# Line 123:
return f"● **Glob** `{pattern}`"

# Line 126:
return f"● **Grep** `{pattern}`"

# Line 129:
return f"● **Task**: {desc}"

# Line 131:
return f"● **TodoWrite**"

# Line 134:
return f"● **{tool_name}**\n`{preview}`"
```

**Step 2: Update parse_mode in _entry_to_messages (line 242, 246)**

```python
messages.append({"text": f"● {entry.text}", "parse_mode": "MarkdownV2"})
# ...
messages.append({"text": text, "parse_mode": "MarkdownV2"})
```

**Step 3: Verify syntax**

Run: `python -m py_compile src/codogram/watcher.py`
Expected: No output (success)

**Step 4: Commit**

```bash
git add src/codogram/watcher.py
git commit -m "fix(watcher): update to GFM bold and MarkdownV2"
```

---

## Task 4: Update permission_poller.py

**Files:**
- Modify: `src/codogram/permission_poller.py`

**Step 1: Replace parse_mode="Markdown" with parse_mode="MarkdownV2"**

Lines to change: 116, 166, 239, 312, 354, 427

Use replace_all:
```
"parse_mode": "Markdown"  →  "parse_mode": "MarkdownV2"
```

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/permission_poller.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "fix(poller): switch to MarkdownV2"
```

---

## Task 5: Update history_watcher.py

**Files:**
- Modify: `src/codogram/history_watcher.py`

**Step 1: Replace parse_mode="Markdown" with parse_mode="MarkdownV2"**

Lines to change: 109, 227, 361

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/history_watcher.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "fix(history): switch to MarkdownV2"
```

---

## Task 6: Update launch_animation.py

**Files:**
- Modify: `src/codogram/launch_animation.py`

**Step 1: Replace parse_mode="Markdown" with parse_mode="MarkdownV2"**

Lines: 79, 85, 92, 116, 124, 133, 145, 156, 171

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/launch_animation.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/codogram/launch_animation.py
git commit -m "fix(animation): switch to MarkdownV2"
```

---

## Task 7: Update services/launch.py

**Files:**
- Modify: `src/codogram/services/launch.py`

**Step 1: Replace parse_mode="Markdown" with parse_mode="MarkdownV2"**

Lines: 113, 124, 133

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/services/launch.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/codogram/services/launch.py
git commit -m "fix(launch): switch to MarkdownV2"
```

---

## Task 8: Update bot.py

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Replace all parse_mode="Markdown" with parse_mode="MarkdownV2"**

~50 occurrences. Use replace_all.

Note: bot.py already uses `**bold**` in some places (auto-accept, settings) — those are correct.

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/bot.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/codogram/bot.py
git commit -m "fix(bot): switch to MarkdownV2"
```

---

## Task 9: Update tests

**Files:**
- Modify: `tests/test_telegram_queue.py`

**Step 1: Remove old escape tests**

Delete tests:
- `test_escape_simple_underscore`
- `test_escape_multiple_underscores`
- `test_preserve_code_block`
- `test_escape_outside_code_block`
- `test_preserve_already_escaped`
- `test_double_underscore`
- `test_no_underscores`
- `test_underscore_in_path`
- `test_our_format_preserved`
- `test_mixed_code_and_text`

Remove import `escape_markdown_underscores` from imports.

**Step 2: Add new test for markdownify integration**

```python
@pytest.mark.asyncio
async def test_markdownv2_messages_are_converted(queue, mock_bot):
    """MarkdownV2 messages should be processed by markdownify."""
    sent_texts = []
    async def capture_send(**kw):
        sent_texts.append(kw.get("text", ""))
        return Mock(message_id=1)
    mock_bot.send_message = AsyncMock(side_effect=capture_send)

    # GFM markdown with header
    batch = OutgoingBatch(1, None, [{"text": "## Header", "parse_mode": "MarkdownV2"}])
    await queue.enqueue(batch)

    # Should be converted (header becomes bold with emoji)
    assert len(sent_texts) == 1
    assert "Header" in sent_texts[0]
    assert "##" not in sent_texts[0]  # Header syntax removed

    await queue.shutdown()
```

**Step 3: Run tests**

Run: `PYTHONPATH=src pytest tests/test_telegram_queue.py -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/test_telegram_queue.py
git commit -m "test(queue): update tests for markdownify"
```

---

## Task 10: Integration test - restart and verify

**Step 1: Restart bot**

Run: `./restart.sh`
Expected: Bot restarted (pid XXXXX)

**Step 2: Check logs for errors**

Run: `tail -20 logs/codogram.log`
Expected: No errors, bot started successfully

**Step 3: Trigger test message**

In Telegram, send a message that will trigger Claude response with GFM markdown.

**Step 4: Verify rendering**

Check that:
- `## Header` renders as bold (not plain text)
- `**bold**` renders as bold
- `- list` renders with bullets
- Our messages (`[v]`, `**Read**`) render correctly

**Step 5: Check for parse errors**

Run: `grep "Parse error" logs/codogram.log | tail -5`
Expected: No new parse errors after restart

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete telegramify-markdown integration"
```

---

## Summary

| Task | Files | Description |
|------|-------|-------------|
| 1 | pyproject.toml | Add dependency |
| 2 | telegram_queue.py | Replace escape with markdownify |
| 3 | watcher.py | Fix bold syntax, MarkdownV2 |
| 4 | permission_poller.py | MarkdownV2 |
| 5 | history_watcher.py | MarkdownV2 |
| 6 | launch_animation.py | MarkdownV2 |
| 7 | services/launch.py | MarkdownV2 |
| 8 | bot.py | MarkdownV2 |
| 9 | tests/ | Update tests |
| 10 | — | Integration test |
