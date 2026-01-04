# Markdown Underscore Escaping

> **Status:** Design approved, ready for implementation

## Problem

Telegram Markdown interprets `_text_` as italic. Claude Code uses `snake_case` heavily in:
- Variable names: `my_variable`
- File paths: `/path/to/file_name.py`
- Tool outputs: `Read file_path`

**Result:** Broken formatting or fallback to plain text.

## Solution

Escape `_` → `\_` in messages with `parse_mode="Markdown"`, except inside `` `code` `` blocks.

### Implementation

Add `escape_markdown_underscores()` to `telegram_queue.py` and apply in `_send_batch()`:

```python
import re

# Pre-compiled for performance
_CODE_BLOCK_RE = re.compile(r'`[^`]*`|[^`]+')
_UNDERSCORE_RE = re.compile(r'(?<!\\)_')


def escape_markdown_underscores(text: str) -> str:
    """Escape underscores outside code blocks for Telegram Markdown.

    Telegram interprets _text_ as italic. Claude Code uses snake_case
    heavily, causing broken formatting.

    Rules:
    - _ → \_ (escape)
    - Inside `code` → leave as is
    - Already escaped \_ → leave as is

    TODO(refactor): Move to adapters/telegram.py
    """
    def process_part(match):
        part = match.group(0)
        if part.startswith('`'):
            return part  # code block - keep as is
        return _UNDERSCORE_RE.sub(r'\\_', part)

    return _CODE_BLOCK_RE.sub(process_part, text)
```

### Application point

In `_send_batch()`, before sending:

```python
for msg in expanded_messages:
    text = msg.get("text", "")
    if msg.get("parse_mode") == "Markdown":
        text = escape_markdown_underscores(text)
    msg["text"] = text

    result = await self.bot.send_message(...)
```

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Algorithm | Regex | 2-3x faster than char-by-char (C implementation) |
| Location | `telegram_queue.py` | Centralized send point, minimal changes |
| Scope | All Markdown messages | Simpler than source-based filtering |
| `\`` edge case | Ignore | Rare in practice, not worth complexity |

## Performance

Benchmarked on typical message sizes:

| Text size | Regex (ms) | Char-by-char (ms) |
|-----------|------------|-------------------|
| Short (45 chars) | 0.005 | 0.006 |
| Medium (900 chars) | 0.07 | 0.18 |
| Long (4500 chars) | 0.31 | 0.87 |

## Tests

```python
def test_escape_simple():
    assert escape_markdown_underscores("var_name") == "var\\_name"

def test_preserve_code_block():
    assert escape_markdown_underscores("`code_block`") == "`code_block`"

def test_escape_outside_code():
    assert escape_markdown_underscores("x `code` var_name") == "x `code` var\\_name"

def test_preserve_already_escaped():
    assert escape_markdown_underscores("already\\_escaped") == "already\\_escaped"

def test_double_underscore():
    assert escape_markdown_underscores("__init__") == "\\_\\_init\\_\\_"
```

## Known Limitations

- **Escaped backticks:** `\`code_block\`` will incorrectly treat content as code block. Rare in practice.
- **MarkdownV2:** Different escaping rules. Out of scope (we use legacy Markdown).

## Migration Path

After bot refactoring (Phase 7+):
1. Move function to `adapters/telegram.py`
2. Update import in `telegram_queue.py`
