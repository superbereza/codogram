# Telegramify-Markdown Integration

> **Status:** Design approved, ready for implementation

## Problem

Claude generates GFM Markdown (headers `##`, `**bold**`, lists `- item`), which doesn't render in Telegram's legacy Markdown mode. Current `escape_markdown_underscores()` only fixes underscores, not the full GFM syntax.

**Symptoms:**
- `## Header` → parse error → fallback to plain text
- `**bold**` → not recognized (legacy uses `*bold*`)
- `- list items` → not rendered as lists

## Solution

Integrate [telegramify-markdown](https://github.com/sudoskys/telegramify-markdown) library to convert GFM → Telegram MarkdownV2.

### Why telegramify-markdown?

- Active development (v0.5.4, Dec 2025)
- Designed for LLM output (our use case)
- Handles: headers, bold, italic, lists, code blocks, quotes
- MIT license

### Why MarkdownV2 over legacy?

| Feature | Legacy Markdown | MarkdownV2 |
|---------|-----------------|------------|
| `**bold**` | ❌ | ✅ |
| `## headers` | ❌ | ✅ (converted to bold) |
| `- lists` | ❌ | ✅ (converted to bullets) |
| `> quotes` | ❌ | ✅ |
| Nested styles | ❌ | ✅ |

## Implementation

### 1. Add dependency

**pyproject.toml:**
```toml
dependencies = [
    "aiogram>=3.4",
    "aiofiles>=23.0",
    "pydantic-settings>=2.0",
    "telegramify-markdown>=0.5",
]
```

### 2. Update telegram_queue.py

Replace `escape_markdown_underscores()` with `telegramify_markdown.markdownify()`:

```python
import telegramify_markdown

# In _send_batch(), before sending:
if msg.get("parse_mode") == "MarkdownV2":
    try:
        msg["text"] = telegramify_markdown.markdownify(msg.get("text", ""))
    except Exception as e:
        logger.warning(f"markdownify failed: {e}, sending as-is")
```

### 3. Update parse_mode everywhere

Find and replace across project:
- `parse_mode="Markdown"` → `parse_mode="MarkdownV2"`

Files affected:
- `telegram_queue.py`
- `permission_poller.py`
- `watcher.py`
- `bot.py`
- `history_watcher.py`
- `launch_animation.py`
- `services/launch.py`

### 4. Update message formatting

GFM uses `**bold**`, legacy used `*bold*`. Update our messages:

```python
# Было (legacy):
f"● *Read* `{path}`"

# Станет (GFM):
f"● **Read** `{path}`"
```

Files to update:
- `watcher.py` — tool formatting
- `strings.py` — if any bold text
- Other places with `*text*` pattern

### 5. Remove old code

Delete `escape_markdown_underscores()` function and its tests.

## Fallback Strategy

Keep existing fallback logic:

```python
except TelegramBadRequest as e:
    if "parse entities" in str(e).lower():
        # Strip parse_mode, retry as plain text
        for msg in batch.messages:
            msg.pop("parse_mode", None)
        return await self._send_batch(batch, attempt + 1)
```

If `markdownify()` produces invalid MarkdownV2, message sends as plain text.

## Testing

### Unit tests
- Remove `test_escape_*` tests
- Add test that `markdownify()` is called for MarkdownV2 messages

### Manual testing
1. Restart bot
2. Trigger Claude response with `##`, `**bold**`, `- list`
3. Verify renders correctly in Telegram
4. Verify our messages (`[v]`, `**Read**`) render correctly
5. Test fallback: send malformed markdown, verify plain text delivery

## Migration from Previous Design

This replaces `docs/designs/done/2025-01-04-markdown-underscore-escaping.md`:
- That design only escaped underscores
- This design fully converts GFM → MarkdownV2
- `escape_markdown_underscores()` will be deleted

## Out of Scope

- Moving all strings to `strings.py` (separate task)
- i18n/localization (not needed)
- Custom markdown symbols configuration

## Risks

| Risk | Mitigation |
|------|------------|
| Library bugs (IndexError, freeze) | Wrap in try/except, fallback to plain text |
| Performance overhead | markdownify is fast, negligible impact |
| Breaking our message format | Test thoroughly before deploy |
