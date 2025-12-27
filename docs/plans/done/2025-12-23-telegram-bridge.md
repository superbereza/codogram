# Telegram-Claude Bridge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Управлять Claude Code с телефона через Telegram — тонкая прослойка для транспорта сообщений.

**Architecture:** tmux для input (send-keys), jsonl для output (watch ~/.claude/projects/). Aiogram для Telegram. Один процесс: бот + watcher.

**Tech Stack:** Python 3.11+, aiogram 3.x, aiofiles, pydantic-settings

**Design Doc:** `docs/designs/codogram.md`

---

## Release 1: Echo Bot + tmux ✅ DONE

**Цель:** Отправить сообщение в Telegram → появится в tmux сессии Claude.

### Task 1.1: Project Skeleton

**Files:**
- Create: `agent-tools/codogram/pyproject.toml`
- Create: `agent-tools/codogram/src/codogram/__init__.py`
- Create: `agent-tools/codogram/src/codogram/config.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "codogram"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "aiogram>=3.4",
    "aiofiles>=23.0",
    "pydantic-settings>=2.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]
```

**Step 2: Create config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    telegram_token: str
    chat_id: int  # Single chat for R1
    project_dir: str  # e.g. /home/user/dev/my-project
    tmux_session: str = "claude-bridge"

    class Config:
        env_file = ".env"

settings = Settings()
```

**Step 3: Create __init__.py**

```python
__version__ = "0.1.0"
```

**Step 4: Commit**

```bash
git add agent-tools/codogram/
git commit -m "feat(codogram): project skeleton"
```

---

### Task 1.2: TmuxSession Class

**Files:**
- Create: `agent-tools/codogram/src/codogram/tmux.py`
- Create: `agent-tools/codogram/tests/test_tmux.py`

**Step 1: Write failing test**

```python
# tests/test_tmux.py
import pytest
from codogram.tmux import TmuxSession

def test_send_escapes_quotes():
    session = TmuxSession("test-session", "/tmp")
    cmd = session._build_send_command("hello 'world'")
    assert "hello" in cmd
    assert "'" in cmd or "\\'" in cmd
```

**Step 2: Run test to verify it fails**

```bash
cd agent-tools/codogram
pytest tests/test_tmux.py -v
```

Expected: FAIL (module not found)

**Step 3: Implement TmuxSession**

```python
# src/codogram/tmux.py
import subprocess
import shlex
from dataclasses import dataclass

@dataclass
class TmuxSession:
    name: str
    cwd: str

    def _build_send_command(self, text: str) -> str:
        escaped = text.replace("'", "'\\''")
        return f"tmux send-keys -t {self.name} '{escaped}' Enter"

    def send(self, text: str) -> None:
        cmd = self._build_send_command(text)
        subprocess.run(cmd, shell=True, check=True)

    def exists(self) -> bool:
        result = subprocess.run(
            f"tmux has-session -t {self.name} 2>/dev/null",
            shell=True
        )
        return result.returncode == 0

    def create(self) -> None:
        if not self.exists():
            subprocess.run(
                f"tmux new-session -d -s {self.name} -c {shlex.quote(self.cwd)}",
                shell=True, check=True
            )

    def attach_command(self) -> str:
        return f"tmux attach -t {self.name}"
```

**Step 4: Run test**

```bash
pytest tests/test_tmux.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat(codogram): TmuxSession class"
```

---

### Task 1.3: Basic Telegram Bot

**Files:**
- Create: `agent-tools/codogram/src/codogram/bot.py`
- Create: `agent-tools/codogram/src/codogram/main.py`

**Step 1: Create bot.py**

```python
# src/codogram/bot.py
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command

from .config import settings
from .tmux import TmuxSession

router = Router()
session: TmuxSession | None = None

def get_session() -> TmuxSession:
    global session
    if session is None:
        session = TmuxSession(settings.tmux_session, settings.project_dir)
        session.create()
    return session

@router.message(Command("start"))
async def cmd_start(message: Message):
    s = get_session()
    await message.answer(
        f"Bridge ready.\n"
        f"Project: `{settings.project_dir}`\n"
        f"Attach: `{s.attach_command()}`",
        parse_mode="Markdown"
    )

@router.message(Command("attach"))
async def cmd_attach(message: Message):
    s = get_session()
    await message.answer(f"`{s.attach_command()}`", parse_mode="Markdown")

@router.message()
async def on_message(message: Message):
    if message.chat.id != settings.chat_id:
        return
    if not message.text:
        return

    s = get_session()
    s.send(message.text)
    await message.answer("◐ sent to claude")
```

**Step 2: Create main.py**

```python
# src/codogram/main.py
import asyncio
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router

async def main():
    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()
    dp.include_router(router)

    print(f"Starting bridge for chat {settings.chat_id}")
    print(f"Project: {settings.project_dir}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 3: Create .env.example**

```bash
TELEGRAM_TOKEN=123456:ABC-DEF
CHAT_ID=-100123456789
PROJECT_DIR=/home/user/dev/my-project
TMUX_SESSION=claude-bridge
```

**Step 4: Test manually**

```bash
cd agent-tools/codogram
cp .env.example .env
# Edit .env with real values
python -m codogram.main
```

Send message in Telegram → check tmux session.

**Step 5: Commit**

```bash
git add -A && git commit -m "feat(codogram): basic telegram bot with tmux send"
```

---

## Release 2: jsonl Watcher + Output ✅ DONE

**Цель:** Ответы Claude из jsonl → появляются в Telegram.

### Task 2.1: JsonlWatcher

**Files:**
- Create: `agent-tools/codogram/src/codogram/watcher.py`
- Create: `agent-tools/codogram/tests/test_watcher.py`

**Step 1: Write failing test**

```python
# tests/test_watcher.py
import pytest
import json
import tempfile
from pathlib import Path

from codogram.watcher import parse_jsonl_entry, ContentType

def test_parse_text_entry():
    entry = {
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": "Hello world"}],
            "stop_reason": "end_turn"
        }
    }
    result = parse_jsonl_entry(entry)
    assert result.content_type == ContentType.TEXT
    assert result.text == "Hello world"

def test_parse_tool_use():
    entry = {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}],
            "stop_reason": "tool_use"
        }
    }
    result = parse_jsonl_entry(entry)
    assert result.content_type == ContentType.TOOL_USE
    assert result.tool_name == "Bash"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_watcher.py -v
```

**Step 3: Implement watcher.py**

```python
# src/codogram/watcher.py
import json
import asyncio
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

class ContentType(Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    UNKNOWN = "unknown"

@dataclass
class ParsedEntry:
    content_type: ContentType
    text: str = ""
    tool_name: str = ""
    tool_input: dict | None = None
    is_complete: bool = False

def parse_jsonl_entry(entry: dict) -> ParsedEntry | None:
    if entry.get("type") != "assistant":
        return None

    message = entry.get("message", {})
    content = message.get("content", [])
    stop_reason = message.get("stop_reason")

    for item in content:
        item_type = item.get("type")

        if item_type == "text":
            return ParsedEntry(
                content_type=ContentType.TEXT,
                text=item.get("text", ""),
                is_complete=stop_reason == "end_turn"
            )
        elif item_type == "tool_use":
            return ParsedEntry(
                content_type=ContentType.TOOL_USE,
                tool_name=item.get("name", ""),
                tool_input=item.get("input"),
                is_complete=False
            )
        elif item_type == "thinking":
            return ParsedEntry(
                content_type=ContentType.THINKING,
                text=item.get("thinking", "")[:100] + "..."
            )

    return None

async def watch_jsonl(path: Path, poll_interval: float = 0.5) -> AsyncIterator[ParsedEntry]:
    """Watch jsonl file and yield new parsed entries."""
    last_position = path.stat().st_size if path.exists() else 0

    while True:
        if not path.exists():
            await asyncio.sleep(poll_interval)
            continue

        current_size = path.stat().st_size
        if current_size > last_position:
            with open(path, "r") as f:
                f.seek(last_position)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        parsed = parse_jsonl_entry(entry)
                        if parsed:
                            yield parsed
                    except json.JSONDecodeError:
                        pass
                last_position = f.tell()

        await asyncio.sleep(poll_interval)
```

**Step 4: Run tests**

```bash
pytest tests/test_watcher.py -v
```

**Step 5: Commit**

```bash
git add -A && git commit -m "feat(codogram): jsonl watcher with parsing"
```

---

### Task 2.2: Integrate Watcher with Bot

**Files:**
- Modify: `agent-tools/codogram/src/codogram/bot.py`
- Modify: `agent-tools/codogram/src/codogram/main.py`

**Step 1: Add watcher task to main.py**

```python
# src/codogram/main.py
import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router, get_session
from .watcher import watch_jsonl, ContentType

def find_jsonl_path() -> Path | None:
    """Find latest jsonl for project."""
    project_hash = settings.project_dir.replace("/", "-").lstrip("-")
    projects_dir = Path.home() / ".claude" / "projects" / project_hash
    if not projects_dir.exists():
        return None
    jsonl_files = sorted(projects_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    return jsonl_files[-1] if jsonl_files else None

async def watcher_task(bot: Bot):
    """Watch jsonl and send updates to Telegram."""
    print("Watcher: waiting for jsonl...")

    while True:
        path = find_jsonl_path()
        if path:
            print(f"Watcher: found {path}")
            break
        await asyncio.sleep(2)

    async for entry in watch_jsonl(path):
        if entry.content_type == ContentType.TEXT:
            symbol = "✓" if entry.is_complete else "◐"
            await bot.send_message(settings.chat_id, f"{symbol} {entry.text[:4000]}")
        elif entry.content_type == ContentType.TOOL_USE:
            await bot.send_message(settings.chat_id, f"◐ {entry.tool_name}")

async def main():
    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()
    dp.include_router(router)

    print(f"Starting bridge for chat {settings.chat_id}")
    print(f"Project: {settings.project_dir}")

    asyncio.create_task(watcher_task(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Update bot.py - remove "sent" confirmation**

```python
# In bot.py, change on_message:
@router.message()
async def on_message(message: Message):
    if message.chat.id != settings.chat_id:
        return
    if not message.text:
        return

    s = get_session()
    s.send(message.text)
    # Don't send confirmation - watcher will show output
```

**Step 3: Test end-to-end**

1. Start Claude Code in tmux: `tmux new -s claude-bridge -c /path/to/project`
2. In tmux: `claude`
3. Start bridge: `python -m codogram.main`
4. Send message in Telegram → see Claude response

**Step 4: Commit**

```bash
git add -A && git commit -m "feat(codogram): integrate jsonl watcher"
```

---

### Task 2.3: Chunking

**Files:**
- Create: `agent-tools/codogram/src/codogram/chunker.py`
- Create: `agent-tools/codogram/tests/test_chunker.py`

**Step 1: Write failing test**

```python
# tests/test_chunker.py
from codogram.chunker import chunk_message

def test_short_message_no_split():
    result = chunk_message("Hello world", max_len=100)
    assert result == ["Hello world"]

def test_long_message_splits():
    text = "A" * 100
    result = chunk_message(text, max_len=30)
    assert len(result) > 1
    assert all(len(c) <= 30 for c in result)

def test_split_on_newline():
    text = "Line1\n\nLine2\n\nLine3"
    result = chunk_message(text, max_len=15)
    assert "Line1" in result[0]
```

**Step 2: Implement chunker.py**

```python
# src/codogram/chunker.py
def chunk_message(text: str, max_len: int = 4000) -> list[str]:
    """Split text into chunks, preferring natural breakpoints."""
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

    # Add prefixes if multiple chunks
    if len(chunks) > 1:
        chunks = [f"[{i+1}/{len(chunks)}]\n{c}" for i, c in enumerate(chunks)]

    return chunks
```

**Step 3: Run tests**

```bash
pytest tests/test_chunker.py -v
```

**Step 4: Integrate into watcher_task**

```python
# In main.py watcher_task:
from .chunker import chunk_message

# Replace send_message with:
if entry.content_type == ContentType.TEXT:
    symbol = "✓" if entry.is_complete else "◐"
    for chunk in chunk_message(entry.text):
        await bot.send_message(settings.chat_id, f"{symbol} {chunk}")
```

**Step 5: Commit**

```bash
git add -A && git commit -m "feat(codogram): message chunking"
```

---

## Release 3: Streaming + Permissions ⚠️ REVISED

**Цель:** Edit-in-place streaming, показ permissions без auto-approve.

**Статус:**
- Task 3.1 (Edit Message Streaming) — ❌ CANCELLED (текст приходит целиком, streaming не нужен)
- Task 3.2 (Permission Display) — ➡️ Moved to `2025-12-23-permissions-and-tool-progress.md`

### Task 3.1: Edit Message Streaming ❌ CANCELLED

**Files:**
- Create: `agent-tools/codogram/src/codogram/streamer.py`

**Step 1: Create streamer.py**

```python
# src/codogram/streamer.py
import asyncio
from aiogram import Bot
from aiogram.types import Message

class EditMessageStreamer:
    """Stream text by editing message in place."""

    def __init__(self, bot: Bot, chat_id: int, min_edit_interval: float = 1.0):
        self.bot = bot
        self.chat_id = chat_id
        self.min_edit_interval = min_edit_interval
        self.message: Message | None = None
        self.buffer = ""
        self.last_edit = 0.0

    async def append(self, text: str, force: bool = False):
        self.buffer += text
        now = asyncio.get_event_loop().time()

        if self.message is None:
            self.message = await self.bot.send_message(self.chat_id, f"◐ {self.buffer[:4000]}")
            self.last_edit = now
        elif force or (now - self.last_edit >= self.min_edit_interval):
            try:
                await self.message.edit_text(f"◐ {self.buffer[:4000]}")
                self.last_edit = now
            except Exception:
                pass  # Message unchanged

    async def complete(self):
        if self.message:
            try:
                await self.message.edit_text(f"✓ {self.buffer[:4000]}")
            except Exception:
                pass
        self.message = None
        self.buffer = ""
```

**Step 2: Integrate into watcher (refactor needed)**

```python
# Update main.py watcher_task to use streamer
# This requires tracking state between entries

async def watcher_task(bot: Bot):
    streamer = EditMessageStreamer(bot, settings.chat_id)
    # ... implementation with streamer.append() and streamer.complete()
```

**Step 3: Commit**

```bash
git add -A && git commit -m "feat(codogram): edit-message streaming"
```

---

### Task 3.2: Permission Display

**Files:**
- Modify: `agent-tools/codogram/src/codogram/watcher.py`
- Modify: `agent-tools/codogram/src/codogram/main.py`

**Step 1: Add permission detection**

Permissions in Claude Code appear as tool_use waiting for approval. The jsonl shows:
- `tool_use` with `stop_reason: "tool_use"`
- Then waiting for user input (no new entries until approved/denied)

**Step 2: Format permission message**

```python
def format_permission(entry: ParsedEntry) -> str:
    """Format tool_use as permission request."""
    name = entry.tool_name
    inp = entry.tool_input or {}

    if name == "Bash":
        cmd = inp.get("command", "")[:200]
        return f"● Bash: `{cmd}`"
    elif name == "Write":
        path = inp.get("file_path", "")
        return f"● Write: `{path}`"
    elif name == "Edit":
        path = inp.get("file_path", "")
        return f"● Edit: `{path}`"
    else:
        return f"● {name}"
```

**Step 3: Show in Telegram (read-only for R3)**

```python
# In watcher_task:
elif entry.content_type == ContentType.TOOL_USE:
    msg = format_permission(entry)
    await bot.send_message(settings.chat_id, msg, parse_mode="Markdown")
```

Note: R3 only shows permissions, doesn't handle approval. User must approve in tmux.

**Step 4: Commit**

```bash
git add -A && git commit -m "feat(codogram): show permission requests"
```

---

## Release 4: Voice + Multi-project

**Цель:** Voice messages через Whisper, несколько проектов через config.

### Task 4.1: Whisper Integration

**Files:**
- Create: `agent-tools/codogram/src/codogram/whisper.py`
- Modify: `agent-tools/codogram/src/codogram/bot.py`
- Modify: `agent-tools/codogram/src/codogram/config.py`

**Step 1: Add openai to dependencies**

```toml
# pyproject.toml
dependencies = [
    "aiogram>=3.4",
    "aiofiles>=23.0",
    "pydantic-settings>=2.0",
    "openai>=1.0",
]
```

**Step 2: Create whisper.py**

```python
# src/codogram/whisper.py
import tempfile
from pathlib import Path
from openai import AsyncOpenAI

from .config import settings

client: AsyncOpenAI | None = None

def get_client() -> AsyncOpenAI:
    global client
    if client is None:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
    return client

async def transcribe(audio_path: Path) -> str:
    """Transcribe audio file using Whisper."""
    c = get_client()
    with open(audio_path, "rb") as f:
        transcript = await c.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="ru"
        )
    return transcript.text
```

**Step 3: Add voice handler to bot.py**

```python
@router.message(F.voice)
async def on_voice(message: Message, bot: Bot):
    if message.chat.id != settings.chat_id:
        return

    # Download voice
    file = await bot.get_file(message.voice.file_id)
    audio_path = Path(tempfile.gettempdir()) / f"{file.file_id}.ogg"

    await bot.download_file(file.file_path, audio_path)

    # Transcribe
    text = await transcribe(audio_path)
    audio_path.unlink()  # cleanup

    # Send to Claude
    s = get_session()
    s.send(text)

    await message.reply(f"◐ {text[:100]}...")
```

**Step 4: Commit**

```bash
git add -A && git commit -m "feat(codogram): whisper voice transcription"
```

---

### Task 4.2: Multi-project Config

**Files:**
- Modify: `agent-tools/codogram/src/codogram/config.py`
- Create: `agent-tools/codogram/config.yaml`

**Step 1: Update config.py**

```python
# src/codogram/config.py
from pathlib import Path
from pydantic_settings import BaseSettings
import yaml

class Settings(BaseSettings):
    telegram_token: str
    openai_api_key: str = ""
    config_path: str = "config.yaml"

    class Config:
        env_file = ".env"

settings = Settings()

def load_projects() -> dict[int, str]:
    """Load chat_id -> project_dir mapping."""
    path = Path(settings.config_path)
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("projects", {})

def get_project_dir(chat_id: int) -> str | None:
    """Get project dir for chat."""
    projects = load_projects()
    return projects.get(chat_id)
```

**Step 2: Create config.yaml example**

```yaml
# config.yaml
projects:
  -100123456789: /home/user/dev/project-a
  -100987654321: /home/user/dev/project-b
```

**Step 3: Update bot.py to use multi-project**

```python
# Replace single chat_id check with:
from .config import get_project_dir

@router.message()
async def on_message(message: Message):
    project_dir = get_project_dir(message.chat.id)
    if not project_dir:
        return  # Unknown chat
    # ... use project_dir for session
```

**Step 4: Commit**

```bash
git add -A && git commit -m "feat(codogram): multi-project config"
```

---

## Summary

| Release | Цель | Ключевые компоненты |
|---------|------|---------------------|
| R1 | Echo Bot + tmux | TmuxSession, basic bot |
| R2 | jsonl → Telegram | JsonlWatcher, chunking |
| R3 | Streaming + Permissions | EditMessageStreamer, permission display |
| R4 | Voice + Multi-project | Whisper, config.yaml |

**После R2** — минимальный работающий bridge.
**После R4** — полнофункциональная версия.
