# Session Binder Design v3

## Проблема

**Баг:** Thread session mixup — когда новая сессия появляется в одном треде (через /start, /new, /compact), другие треды ошибочно теряют свою привязку.

**Root cause:** `check_session_for_thread()` использует `find_session_for_project(cwd)` который возвращает последнюю сессию **проекта**, а не сессию конкретного треда.

## Решение

Двухуровневая система binding:

1. **Primary: Hooks** — Claude вызывает hook при смене сессии, передаёт session_id + tmux_session
2. **Fallback: Content matching** — для сессий без hooks, матчим контент jsonl с capture-pane

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                         Claude                               │
│  (SessionStart hook → session_hook.sh → HTTP POST)          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    HookServer (adapter)                      │
│  - Слушает на порту HOOK_SERVER_PORT                        │
│  - Получает: session_id, cwd, tmux_session                  │
│  - Вызывает: session_binder.bind_from_hook()                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 SessionBinderService (service)               │
│  - bind_from_hook(): точная привязка через hook             │
│  - check_and_bind(): fallback через content matching        │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌─────────────────────┐    ┌─────────────────────────────────┐
│   HistoryWatcher    │    │        on_message handler       │
│   (каждые 15 сек)   │    │   (при сообщении пользователя)  │
└─────────────────────┘    └─────────────────────────────────┘
```

## Файловая структура

```
src/codogram/
├── adapters/
│   ├── __init__.py
│   ├── hook_server.py        # HTTP сервер для hooks
│   └── tmux.py               # capture_pane и др.
│
├── services/
│   ├── __init__.py
│   └── session_binder.py     # SessionBinderService
│
├── scripts/
│   └── setup_hooks.py        # CLI для настройки hooks
│
└── hooks/
    └── session_hook.sh       # Скрипт для Claude SessionStart hook
```

## Конфигурация

**.env:**
```bash
# Hooks
HOOKS_ENABLED=true           # false для тестирования без hooks
HOOK_SERVER_PORT=8787        # Порт для hook server

# Существующие
TELEGRAM_TOKEN=...
ADMIN_IDS=...
```

**config.py:**
```python
@dataclass
class Config:
    # ... existing ...

    hooks_enabled: bool = True
    hook_server_port: int = 8787

    @classmethod
    def from_env(cls):
        return cls(
            # ... existing ...
            hooks_enabled=os.getenv("HOOKS_ENABLED", "true").lower() == "true",
            hook_server_port=int(os.getenv("HOOK_SERVER_PORT", "8787")),
        )
```

## Компоненты

### 1. HookServer (adapters/hook_server.py)

```python
"""HTTP server for receiving Claude session hooks."""

import asyncio
from aiohttp import web
from ..logging_config import logger


class HookServer:
    """Receives SessionStart hooks from Claude."""

    def __init__(self, port: int, on_session_hook):
        self.port = port
        self.on_session_hook = on_session_hook
        self._app = None
        self._runner = None

    async def start(self):
        """Start the HTTP server."""
        self._app = web.Application()
        self._app.router.add_post('/hook/session-start', self._handle_session_start)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, '127.0.0.1', self.port)
        await site.start()

        logger.info(f"hook_server_started: port={self.port}")

    async def stop(self):
        """Stop the HTTP server."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("hook_server_stopped")

    async def _handle_session_start(self, request: web.Request) -> web.Response:
        """Handle SessionStart hook from Claude."""
        try:
            data = await request.json()

            session_id = data.get('session_id')
            cwd = data.get('cwd')
            tmux_session = data.get('tmux_session')

            if not session_id:
                logger.warning("hook_missing_session_id")
                return web.Response(text='missing session_id', status=400)

            logger.info(f"hook_received: session={session_id[:8]}, tmux={tmux_session}, cwd={cwd}")

            # Call the callback
            await self.on_session_hook(session_id, cwd, tmux_session)

            return web.Response(text='ok')

        except Exception as e:
            logger.error(f"hook_error: {e}")
            return web.Response(text='error', status=500)
```

### 2. session_hook.sh (hooks/session_hook.sh)

```bash
#!/bin/bash
# Claude Code SessionStart hook
# Sends session info to codogram hook server

set -e

# Read JSON input from Claude
input=$(cat)

# Parse fields
session_id=$(echo "$input" | jq -r '.session_id // empty')
cwd=$(echo "$input" | jq -r '.cwd // empty')

if [ -z "$session_id" ]; then
    exit 0
fi

# Detect tmux session name
tmux_session=$(tmux display-message -p '#S' 2>/dev/null || echo "")

# Get port from environment or use default
HOOK_PORT="${CODOGRAM_HOOK_PORT:-8787}"

# Send to hook server
curl -s -X POST "http://127.0.0.1:${HOOK_PORT}/hook/session-start" \
    -H "Content-Type: application/json" \
    -d "{
        \"session_id\": \"$session_id\",
        \"cwd\": \"$cwd\",
        \"tmux_session\": \"$tmux_session\"
    }" >/dev/null 2>&1 || true

exit 0
```

### 3. setup_hooks.py (scripts/setup_hooks.py)

```python
#!/usr/bin/env python3
"""CLI tool to configure Claude hooks for codogram."""

import json
import shutil
from pathlib import Path


CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK_SCRIPT = Path(__file__).parent.parent / "hooks" / "session_hook.sh"


def setup_hooks(port: int = 8787) -> bool:
    """Add SessionStart hook to Claude settings.

    Returns True if hooks were configured, False if user declined.
    """
    print("=== Codogram Hooks Setup ===\n")

    # Check if hook script exists
    if not HOOK_SCRIPT.exists():
        print(f"Error: Hook script not found at {HOOK_SCRIPT}")
        return False

    # Make hook script executable
    HOOK_SCRIPT.chmod(0o755)

    # Load existing settings
    settings = {}
    if CLAUDE_SETTINGS.exists():
        with open(CLAUDE_SETTINGS) as f:
            settings = json.load(f)

    # Check if hook already configured
    hooks = settings.get("hooks", {})
    session_start = hooks.get("SessionStart", [])

    hook_command = f'CODOGRAM_HOOK_PORT={port} {HOOK_SCRIPT}'

    already_configured = any(
        hook_command in str(h.get("hooks", []))
        for h in session_start
    )

    if already_configured:
        print("Hooks already configured!")
        return True

    # Show what we're going to do
    print(f"This will add a SessionStart hook to {CLAUDE_SETTINGS}")
    print(f"Hook command: {hook_command}")
    print()

    # Ask for confirmation
    response = input("Proceed? [y/N]: ").strip().lower()
    if response != 'y':
        print("Aborted.")
        return False

    # Backup existing settings
    if CLAUDE_SETTINGS.exists():
        backup = CLAUDE_SETTINGS.with_suffix('.json.bak')
        shutil.copy(CLAUDE_SETTINGS, backup)
        print(f"Backed up existing settings to {backup}")

    # Add hook
    new_hook = {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": hook_command
            }
        ]
    }

    if "hooks" not in settings:
        settings["hooks"] = {}
    if "SessionStart" not in settings["hooks"]:
        settings["hooks"]["SessionStart"] = []

    settings["hooks"]["SessionStart"].append(new_hook)

    # Save
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAUDE_SETTINGS, 'w') as f:
        json.dump(settings, f, indent=2)

    print(f"\nHooks configured successfully!")
    print(f"Restart any running Claude sessions for hooks to take effect.")
    return True


def remove_hooks() -> bool:
    """Remove codogram hooks from Claude settings."""
    if not CLAUDE_SETTINGS.exists():
        print("No Claude settings found.")
        return True

    with open(CLAUDE_SETTINGS) as f:
        settings = json.load(f)

    hooks = settings.get("hooks", {})
    session_start = hooks.get("SessionStart", [])

    # Filter out codogram hooks
    filtered = [
        h for h in session_start
        if "session_hook.sh" not in str(h.get("hooks", []))
    ]

    if len(filtered) == len(session_start):
        print("No codogram hooks found.")
        return True

    settings["hooks"]["SessionStart"] = filtered

    with open(CLAUDE_SETTINGS, 'w') as f:
        json.dump(settings, f, indent=2)

    print("Codogram hooks removed.")
    return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "remove":
        remove_hooks()
    else:
        setup_hooks()
```

### 4. SessionBinderService (services/session_binder.py)

```python
"""Session binding service with hooks and content matching fallback."""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging_config import logger
from ..session_manager import ProjectState, ThreadInfo, project_manager
from ..history_reader import compute_jsonl_path

if TYPE_CHECKING:
    from ..adapters.hook_server import HookServer


class SessionBinderService:
    """Binds Claude sessions to threads.

    Primary: Hooks (exact tmux↔session mapping)
    Fallback: Content matching (for sessions without hooks)
    """

    def __init__(self, config, tmux_adapter, history_adapter):
        self.config = config
        self.tmux = tmux_adapter
        self.history = history_adapter
        self.hook_server: "HookServer | None" = None

    async def start_hook_server(self):
        """Start hook server if enabled."""
        if not self.config.hooks_enabled:
            logger.info("hooks_disabled: skipping hook server")
            return

        from ..adapters.hook_server import HookServer

        self.hook_server = HookServer(
            port=self.config.hook_server_port,
            on_session_hook=self.bind_from_hook
        )
        await self.hook_server.start()

    async def stop_hook_server(self):
        """Stop hook server."""
        if self.hook_server:
            await self.hook_server.stop()

    # === Primary: Hook-based binding ===

    async def bind_from_hook(self, session_id: str, cwd: str, tmux_session: str):
        """Bind session from hook data. Called by HookServer."""
        logger.debug(f"bind_from_hook: session={session_id[:8]}, tmux={tmux_session}, cwd={cwd}")

        # Find project by cwd
        project = self._find_project_by_cwd(cwd)
        if not project:
            logger.warning(f"hook_no_project: cwd={cwd}")
            return

        # Find thread by tmux session name
        thread = self._find_thread_by_tmux(project, tmux_session)
        if not thread:
            logger.warning(f"hook_no_thread: tmux={tmux_session}, project={project.project_name}")
            return

        # Check if session actually changed
        if thread.session_id == session_id:
            logger.debug(f"hook_same_session: {session_id[:8]}")
            return

        logger.info(f"hook_bind: project={project.project_name}, thread={thread.name}, "
                   f"old={thread.session_id[:8] if thread.session_id else None}, new={session_id[:8]}")

        await self._rebind_thread(project, thread, session_id)

    def _find_project_by_cwd(self, cwd: str) -> ProjectState | None:
        """Find project by working directory."""
        for project in project_manager.projects.values():
            if project.cwd == cwd:
                return project
        return None

    def _find_thread_by_tmux(self, project: ProjectState, tmux_session: str) -> ThreadInfo | None:
        """Find thread by tmux session name."""
        for thread in project.threads.values():
            expected_tmux = thread.get_tmux_session(project.project_name)
            if expected_tmux == tmux_session:
                return thread
        return None

    # === Fallback: Content matching ===

    async def check_and_bind(self, project: ProjectState):
        """Check for unbound sessions and try to bind via content matching.

        Called by HistoryWatcher and on_message as fallback when hooks not available.
        """
        if self._is_multi_thread(project):
            await self._bind_multi_thread(project)
        else:
            await self._bind_single_thread(project)

    def _is_multi_thread(self, project: ProjectState) -> bool:
        """Project is multi-thread if has topics (thread_id != None)."""
        return any(t.thread_id is not None for t in project.threads.values())

    async def _bind_single_thread(self, project: ProjectState):
        """Legacy binding for single-thread projects."""
        thread = project.threads.get(None)
        if not thread:
            return

        new_session = self.history.find_session_for_project(project.cwd)

        if new_session and new_session != thread.session_id:
            logger.info(f"fallback_bind_single: {thread.session_id} -> {new_session}")
            await self._rebind_thread(project, thread, new_session)

    async def _bind_multi_thread(self, project: ProjectState):
        """Content matching for multi-thread projects."""
        unbound = self._find_unbound_sessions(project)

        for session_id in unbound:
            await self._try_bind_via_content(project, session_id)

    def _find_unbound_sessions(self, project: ProjectState) -> set[str]:
        """Find sessions not bound to any thread."""
        project_dir = self._get_project_dir(project.cwd)
        if not project_dir.exists():
            return set()

        all_sessions = {f.stem for f in project_dir.glob("*.jsonl")}
        bound = {t.session_id for t in project.threads.values() if t.session_id}
        return all_sessions - bound

    def _get_project_dir(self, cwd: str) -> Path:
        """Get project directory for jsonl files."""
        normalized = cwd.rstrip("/") or "/"
        while "//" in normalized:
            normalized = normalized.replace("//", "/")
        project_hash = normalized.replace("/", "-")
        return Path.home() / ".claude" / "projects" / project_hash

    async def _try_bind_via_content(self, project: ProjectState, session_id: str):
        """Try to match session content with tmux capture-pane."""
        jsonl_path = compute_jsonl_path(project.cwd, session_id)
        content = self._extract_matchable_content(jsonl_path)

        if not content:
            logger.debug(f"fallback_no_content: session={session_id[:8]}")
            return

        logger.debug(f"fallback_trying: session={session_id[:8]}, content={content[:50]}...")

        for thread in project.threads.values():
            if thread.session_id:
                continue  # Already bound

            tmux_name = thread.get_tmux_session(project.project_name)
            pane = self.tmux.capture_pane(tmux_name)

            if self._content_matches(content, pane):
                logger.info(f"fallback_bind_content: thread={thread.name}, session={session_id[:8]}")
                await self._rebind_thread(project, thread, session_id)
                break
        else:
            logger.debug(f"fallback_no_match: session={session_id[:8]}")

    def _extract_matchable_content(self, jsonl_path: Path) -> str | None:
        """Extract content for matching from last assistant entry."""
        last_entry = self.history.read_last_assistant_entry(jsonl_path)
        if not last_entry:
            return None

        content = last_entry.get("message", {}).get("content", [])

        for item in content:
            if item.get("type") == "text":
                return item.get("text", "")[:200]
            elif item.get("type") == "tool_use":
                name = item.get("name", "")
                inp = str(item.get("input", {}))[:100]
                return f"tool:{name}:{inp}"

        return None

    def _content_matches(self, content: str, pane: str) -> bool:
        """Check if content appears in tmux pane."""
        if not content or not pane:
            return False

        if content.startswith("tool:"):
            parts = content.split(":", 2)
            if len(parts) < 3:
                logger.warning(f"fallback_malformed_tool: {content}")
                return False
            _, tool_name, tool_input = parts
            return tool_name in pane and tool_input[:50] in pane
        else:
            return content[:150] in pane

    # === Rebind ===

    async def _rebind_thread(self, project: ProjectState, thread: ThreadInfo, new_session_id: str):
        """Rebind thread to new session."""
        # Cancel old watcher
        if thread.watcher_task:
            thread.watcher_task.cancel()
            thread.watcher_task = None

        # Update binding
        old_session = thread.session_id
        thread.session_id = new_session_id
        thread.jsonl_path = str(compute_jsonl_path(project.cwd, new_session_id))

        logger.info(f"session_rebound: project={project.project_name}, thread={thread.name}, "
                   f"old={old_session[:8] if old_session else None}, new={new_session_id[:8]}")

        # Start new watcher
        from ..history_watcher import watch_thread_jsonl
        # Note: need to get telegram_queue from somewhere - will be injected
        # thread.watcher_task = asyncio.create_task(watch_thread_jsonl(...))

        # Save config
        project_manager._save()
```

### 5. TmuxAdapter addition (adapters/tmux.py)

```python
def capture_pane(self, session_name: str) -> str:
    """Capture entire scrollback from tmux pane.

    Uses -S - to get full history, not just visible area.
    """
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.debug(f"capture_pane_failed: {session_name}, rc={result.returncode}")
        return ""
    return result.stdout
```

## Интеграция

### main.py

```python
async def main():
    # ... existing setup ...

    # Create session binder
    from .services.session_binder import SessionBinderService
    session_binder = SessionBinderService(config, tmux_adapter, history_adapter)

    # Start hook server if enabled
    await session_binder.start_hook_server()

    # Pass to HistoryWatcher
    history_watcher = HistoryWatcher(bot, ..., session_binder=session_binder)

    # ... rest of startup ...

    # On shutdown
    await session_binder.stop_hook_server()
```

### HistoryWatcher

```python
async def _check_for_changes(self):
    for project in self.project_manager.projects.values():
        # ... cleanup checks ...

        # Fallback binding (for sessions without hooks)
        await self.session_binder.check_and_bind(project)
```

### on_message (handlers/messages.py)

```python
async def on_message(message: Message, session_binder: SessionBinderService):
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        return

    # Check for session changes (fallback)
    await session_binder.check_and_bind(project)

    # ... rest of message handling ...
```

## Что удаляем

1. **`check_session_for_thread()`** в `history_watcher.py` — заменяется на SessionBinderService
2. Вызов `check_session_for_thread` в `bot.py` on_message

## Что остаётся

1. **`poll_for_session_thread()`** — binding по user message (для новых тредов)
2. **`watch_thread_jsonl()`** — watcher для треда
3. **`find_session_for_project()`** — используется в fallback для single-thread

## Тестирование

### С hooks:
```bash
# 1. Setup hooks
python -m codogram.scripts.setup_hooks

# 2. Restart Claude sessions

# 3. Test /compact in a topic
# Expected: immediate rebind via hook
```

### Без hooks (fallback):
```bash
# 1. Set HOOKS_ENABLED=false in .env

# 2. Restart bot

# 3. Test /compact in a topic
# Expected: rebind via content matching within 15 sec
```

## Rollout

1. Добавить adapters/hook_server.py
2. Добавить services/session_binder.py
3. Добавить hooks/session_hook.sh
4. Добавить scripts/setup_hooks.py
5. Добавить capture_pane в tmux.py
6. Обновить config.py с hooks settings
7. Интегрировать в main.py
8. Интегрировать в HistoryWatcher
9. Удалить check_session_for_thread
10. Тестирование с hooks
11. Тестирование без hooks (fallback)
12. Документация для пользователей

## Changelog

**v3 (2025-12-29):**
- Added hooks as primary binding mechanism
- Content matching becomes fallback
- Added HookServer, setup_hooks.py, session_hook.sh
- Added configuration for enabling/disabling hooks

**v2 (2025-12-29):**
- ValueError fix for tool content parsing
- Full tmux scrollback capture (-S -)
- Reuse compute_jsonl_path()
- Added logging

**v1 (2025-12-29):**
- Initial design with content matching only
