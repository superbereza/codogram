# Multi-Session Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Перейти от одного захардкоженного чата к архитектуре с несколькими сессиями и группами.

**Architecture:** HTTP server принимает регистрации от Claude hooks, Session Manager управляет сессиями и маппингом project→chat, существующие poller/watcher адаптируются для работы с несколькими сессиями.

**Tech Stack:** Python, aiogram, aiohttp (HTTP server), pydantic

---

### Task 1: Update .gitignore

**Files:**
- Modify: `agent-tools/telegram-bridge/.gitignore`

**Step 1: Add config files to gitignore**

```gitignore
.env
.config.json
__pycache__/
*.pyc
```

**Step 2: Commit**

```bash
git add agent-tools/telegram-bridge/.gitignore
git commit -m "chore(telegram-bridge): add .config.json to gitignore"
```

---

### Task 2: Create project_resolver.py

**Files:**
- Create: `agent-tools/telegram-bridge/src/telegram_bridge/project_resolver.py`
- Create: `agent-tools/telegram-bridge/tests/test_project_resolver.py`

**Step 1: Write the failing test**

```python
# tests/test_project_resolver.py
import pytest
from pathlib import Path
from telegram_bridge.project_resolver import get_project_name

def test_simple_directory():
    """Directory without git returns its name."""
    result = get_project_name(Path("/dev/personal-agent"))
    assert result == "personal-agent"

def test_git_repo(tmp_path):
    """Git repo returns directory name."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    result = get_project_name(tmp_path)
    assert result == tmp_path.name

def test_worktree(tmp_path):
    """Worktree returns main repo name."""
    # Create fake worktree .git file
    git_file = tmp_path / ".git"
    main_repo = Path("/dev/personal-agent")
    git_file.write_text(f"gitdir: {main_repo}/.git/worktrees/feature-x")

    result = get_project_name(tmp_path)
    assert result == "personal-agent"
```

**Step 2: Run test to verify it fails**

```bash
cd agent-tools/telegram-bridge
source ../../venv/bin/activate
python -m pytest tests/test_project_resolver.py -v
```

Expected: FAIL with "No module named 'telegram_bridge.project_resolver'"

**Step 3: Write implementation**

```python
# src/telegram_bridge/project_resolver.py
from pathlib import Path

def get_project_name(cwd: Path) -> str:
    """
    Get project name for chat mapping.
    Worktree -> main repository name.
    """
    git_path = cwd / ".git"

    # Worktree: .git is a file with gitdir
    if git_path.is_file():
        content = git_path.read_text().strip()
        if content.startswith("gitdir:"):
            gitdir = Path(content.split(":", 1)[1].strip())
            # .git/worktrees/xxx -> .git -> repo folder
            main_repo = gitdir.parent.parent.parent
            return main_repo.name

    # Regular repo or no git - folder name
    return cwd.name
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_project_resolver.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/project_resolver.py agent-tools/telegram-bridge/tests/test_project_resolver.py
git commit -m "feat(telegram-bridge): add project_resolver for worktree support"
```

---

### Task 3: Update config.py

**Files:**
- Modify: `agent-tools/telegram-bridge/src/telegram_bridge/config.py`

**Step 1: Update Settings class**

```python
# src/telegram_bridge/config.py
import json
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    telegram_token: str
    admin_chat_id: int  # Personal chat for alerts (renamed from chat_id)
    base_dir: str  # e.g. /home/user/dev
    http_port: int = 8787

    class Config:
        env_file = ".env"

settings = Settings()

# Config file path
CONFIG_PATH = Path(__file__).parent.parent.parent / ".config.json"

def load_config() -> dict:
    """Load .config.json or return default."""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"projects": {}, "sessions": {}}

def save_config(config: dict) -> None:
    """Save config to .config.json."""
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
```

**Step 2: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/config.py
git commit -m "feat(telegram-bridge): update config for multi-session support"
```

---

### Task 4: Create session_manager.py

**Files:**
- Create: `agent-tools/telegram-bridge/src/telegram_bridge/session_manager.py`

**Step 1: Write SessionManager class**

```python
# src/telegram_bridge/session_manager.py
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Awaitable

from .config import settings, load_config, save_config
from .project_resolver import get_project_name
from .tmux import TmuxSession

@dataclass
class SessionState:
    session_id: str
    tmux_session: str
    cwd: str
    project_name: str
    jsonl_path: str | None = None
    chat_id: int | None = None
    poller_task: asyncio.Task | None = field(default=None, repr=False)
    watcher_task: asyncio.Task | None = field(default=None, repr=False)

class SessionManager:
    def __init__(self):
        self.sessions: dict[str, SessionState] = {}
        self.projects: dict[str, int] = {}  # project_name -> chat_id
        self._config = load_config()
        self.projects = self._config.get("projects", {})

    def _save(self) -> None:
        """Persist config to disk."""
        self._config["projects"] = self.projects
        self._config["sessions"] = {
            sid: {
                "tmux_session": s.tmux_session,
                "cwd": s.cwd,
                "project_name": s.project_name,
                "jsonl_path": s.jsonl_path,
            }
            for sid, s in self.sessions.items()
        }
        save_config(self._config)

    def register_project(self, project_name: str, chat_id: int) -> None:
        """Register project -> chat mapping."""
        self.projects[project_name] = chat_id
        self._save()

    def get_chat_id(self, project_name: str) -> int | None:
        """Get chat_id for project."""
        return self.projects.get(project_name)

    def get_session_by_chat(self, chat_id: int) -> SessionState | None:
        """Find active session for chat_id."""
        for session in self.sessions.values():
            if session.chat_id == chat_id:
                return session
        return None

    async def register_session(
        self,
        session_id: str,
        cwd: str,
        tmux_session: str,
        start_poller: Callable[[SessionState], Awaitable[asyncio.Task]],
        start_watcher: Callable[[SessionState], Awaitable[asyncio.Task]],
    ) -> SessionState | None:
        """Register new Claude session."""
        project_name = get_project_name(Path(cwd))
        chat_id = self.get_chat_id(project_name)

        # Find jsonl path
        project_hash = cwd.replace("/", "-")
        projects_dir = Path.home() / ".claude" / "projects" / project_hash
        jsonl_path = None
        if projects_dir.exists():
            jsonl_files = sorted(projects_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
            if jsonl_files:
                jsonl_path = str(jsonl_files[-1])

        session = SessionState(
            session_id=session_id,
            tmux_session=tmux_session,
            cwd=cwd,
            project_name=project_name,
            jsonl_path=jsonl_path,
            chat_id=chat_id,
        )

        self.sessions[session_id] = session

        # Start tasks only if we have chat_id
        if chat_id:
            session.poller_task = await start_poller(session)
            if jsonl_path:
                session.watcher_task = await start_watcher(session)

        self._save()
        return session

    async def unregister_session(self, session_id: str) -> None:
        """Unregister Claude session."""
        session = self.sessions.pop(session_id, None)
        if session:
            if session.poller_task:
                session.poller_task.cancel()
            if session.watcher_task:
                session.watcher_task.cancel()
        self._save()

    async def restore_sessions(
        self,
        start_poller: Callable[[SessionState], Awaitable[asyncio.Task]],
        start_watcher: Callable[[SessionState], Awaitable[asyncio.Task]],
    ) -> None:
        """Restore sessions from config after bot restart."""
        saved_sessions = self._config.get("sessions", {})
        for session_id, data in saved_sessions.items():
            chat_id = self.get_chat_id(data["project_name"])
            session = SessionState(
                session_id=session_id,
                tmux_session=data["tmux_session"],
                cwd=data["cwd"],
                project_name=data["project_name"],
                jsonl_path=data.get("jsonl_path"),
                chat_id=chat_id,
            )
            self.sessions[session_id] = session

            if chat_id:
                # Verify tmux session still exists
                tmux = TmuxSession(session.tmux_session, session.cwd)
                if tmux.exists():
                    session.poller_task = await start_poller(session)
                    if session.jsonl_path:
                        session.watcher_task = await start_watcher(session)

manager = SessionManager()
```

**Step 2: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/session_manager.py
git commit -m "feat(telegram-bridge): add SessionManager for multi-session support"
```

---

### Task 5: Create Claude hooks

**Files:**
- Create: `agent-tools/telegram-bridge/hooks/session-start.sh`
- Create: `agent-tools/telegram-bridge/hooks/session-end.sh`

**Step 1: Create session-start.sh**

```bash
#!/bin/bash
# Claude Code SessionStart hook
# Registers session with telegram-bridge

set -e

# Read JSON input from Claude
input=$(cat)

session_id=$(echo "$input" | jq -r '.session_id // empty')
cwd=$(echo "$input" | jq -r '.cwd // empty')

if [ -z "$session_id" ]; then
    exit 0
fi

# Detect tmux session
tmux_session=$(tmux display-message -p '#S' 2>/dev/null || echo "")

# Register with telegram-bridge (fire and forget)
curl -s -X POST "http://localhost:8787/session/register" \
    -H "Content-Type: application/json" \
    -d "{
        \"session_id\": \"$session_id\",
        \"cwd\": \"$cwd\",
        \"tmux_session\": \"$tmux_session\"
    }" >/dev/null 2>&1 || true

exit 0
```

**Step 2: Create session-end.sh**

```bash
#!/bin/bash
# Claude Code SessionEnd hook
# Unregisters session from telegram-bridge

set -e

input=$(cat)
session_id=$(echo "$input" | jq -r '.session_id // empty')

if [ -z "$session_id" ]; then
    exit 0
fi

curl -s -X POST "http://localhost:8787/session/unregister" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$session_id\"}" >/dev/null 2>&1 || true

exit 0
```

**Step 3: Make executable**

```bash
chmod +x agent-tools/telegram-bridge/hooks/session-start.sh
chmod +x agent-tools/telegram-bridge/hooks/session-end.sh
```

**Step 4: Commit**

```bash
git add agent-tools/telegram-bridge/hooks/
git commit -m "feat(telegram-bridge): add Claude Code session hooks"
```

---

### Task 6: Add HTTP server to main.py

**Files:**
- Modify: `agent-tools/telegram-bridge/src/telegram_bridge/main.py`

**Step 1: Add aiohttp to requirements**

```bash
echo "aiohttp" >> agent-tools/telegram-bridge/requirements.txt
pip install aiohttp
```

**Step 2: Update main.py with HTTP server**

Replace main.py content - add HTTP server running alongside Telegram bot. Key changes:
- Add `/session/register` and `/session/unregister` endpoints
- Use SessionManager instead of hardcoded session
- Start both HTTP server and Telegram polling

```python
# src/telegram_bridge/main.py
import asyncio
from pathlib import Path
from aiohttp import web
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router
from .session_manager import manager, SessionState
from .tmux import TmuxSession

# HTTP handlers
async def handle_register(request: web.Request) -> web.Response:
    """Handle session registration from Claude hook."""
    data = await request.json()
    session_id = data.get("session_id")
    cwd = data.get("cwd")
    tmux_session = data.get("tmux_session")

    if not session_id or not cwd:
        return web.json_response({"error": "missing fields"}, status=400)

    bot = request.app["bot"]

    async def start_poller(session: SessionState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return asyncio.create_task(create_poller_task(bot, session))

    async def start_watcher(session: SessionState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return asyncio.create_task(create_watcher_task(bot, session))

    session = await manager.register_session(
        session_id=session_id,
        cwd=cwd,
        tmux_session=tmux_session or "unknown",
        start_poller=start_poller,
        start_watcher=start_watcher,
    )

    return web.json_response({
        "status": "registered",
        "project": session.project_name,
        "has_chat": session.chat_id is not None,
    })

async def handle_unregister(request: web.Request) -> web.Response:
    """Handle session unregistration from Claude hook."""
    data = await request.json()
    session_id = data.get("session_id")

    if not session_id:
        return web.json_response({"error": "missing session_id"}, status=400)

    await manager.unregister_session(session_id)
    return web.json_response({"status": "unregistered"})

async def run_http_server(bot: Bot) -> None:
    """Run HTTP server for session registration."""
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/session/register", handle_register)
    app.router.add_post("/session/unregister", handle_unregister)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", settings.http_port)
    await site.start()
    print(f"HTTP server running on http://localhost:{settings.http_port}")

async def main():
    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()
    dp.include_router(router)

    print(f"Starting bridge")
    print(f"Admin chat: {settings.admin_chat_id}")
    print(f"Base dir: {settings.base_dir}")

    # Start HTTP server
    await run_http_server(bot)

    # Restore sessions from config
    async def start_poller(session: SessionState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return asyncio.create_task(create_poller_task(bot, session))

    async def start_watcher(session: SessionState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return asyncio.create_task(create_watcher_task(bot, session))

    await manager.restore_sessions(start_poller, start_watcher)

    # Start Telegram polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 3: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/main.py agent-tools/telegram-bridge/requirements.txt
git commit -m "feat(telegram-bridge): add HTTP server for session registration"
```

---

### Task 7: Update bot.py for multi-session

**Files:**
- Modify: `agent-tools/telegram-bridge/src/telegram_bridge/bot.py`

**Step 1: Update bot.py**

Key changes:
- Remove hardcoded session, use SessionManager
- Route messages by chat_id
- Add /register_dir and /status commands
- Auto-register project when bot added to group

```python
# src/telegram_bridge/bot.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from .config import settings
from .session_manager import manager
from .tmux import TmuxSession
from .state import permission_messages

router = Router()

def get_session_for_chat(chat_id: int) -> TmuxSession | None:
    """Get TmuxSession for chat_id."""
    session = manager.get_session_by_chat(chat_id)
    if session:
        return TmuxSession(session.tmux_session, session.cwd)
    return None

@router.message(Command("start"))
async def cmd_start(message: Message):
    # Auto-register project by chat title
    if message.chat.title:
        existing = manager.get_chat_id(message.chat.title)
        if not existing:
            manager.register_project(message.chat.title, message.chat.id)

    session = manager.get_session_by_chat(message.chat.id)
    if session:
        tmux = TmuxSession(session.tmux_session, session.cwd)
        text = f"Bridge active.\nProject: `{session.project_name}`\nAttach: `{tmux.attach_command()}`"
    else:
        text = "Bridge ready. No active Claude session."

    try:
        await message.answer(text, parse_mode="Markdown")
    except Exception:
        await message.answer(text)

@router.message(Command("status"))
async def cmd_status(message: Message):
    session = manager.get_session_by_chat(message.chat.id)
    if session:
        text = f"Active session: `{session.session_id[:8]}...`\nProject: `{session.project_name}`\ntmux: `{session.tmux_session}`"
    else:
        text = "No active session for this chat."

    try:
        await message.answer(text, parse_mode="Markdown")
    except Exception:
        await message.answer(text)

@router.message(Command("register_dir"))
async def cmd_register_dir(message: Message):
    if not message.text:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /register_dir <path>\nExample: /register_dir personal-agent")
        return

    path = parts[1].strip()
    # path is relative to base_dir
    project_name = path.split("/")[-1]

    manager.register_project(project_name, message.chat.id)
    await message.answer(f"Registered `{project_name}` for this chat.", parse_mode="Markdown")

@router.message(Command("esc"))
async def cmd_esc(message: Message):
    tmux = get_session_for_chat(message.chat.id)
    if tmux:
        tmux.send_key("Escape")

@router.callback_query(F.data.startswith("perm:"))
async def on_permission_callback(callback: CallbackQuery):
    """Handle permission button press."""
    chat_id = callback.message.chat.id
    kb_msg_id = callback.message.message_id

    # Delete content messages
    content_ids = permission_messages.pop(kb_msg_id, [])
    for msg_id in content_ids:
        try:
            await callback.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    # Delete keyboard message
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Send key to tmux
    action = callback.data.split(":")[1]
    tmux = get_session_for_chat(chat_id)

    if tmux:
        if action == "esc":
            tmux.send_key("Escape")
        else:
            tmux.send_key(action)

    await callback.answer()

@router.message()
async def on_message(message: Message):
    if not message.text:
        return

    tmux = get_session_for_chat(message.chat.id)
    if tmux:
        tmux.send(message.text)
    else:
        # No active session
        if message.chat.id != settings.admin_chat_id:
            await message.answer("No active Claude session. Start Claude in this project first.")
```

**Step 2: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): update bot for multi-session routing"
```

---

### Task 8: Update permission_poller.py for multi-session

**Files:**
- Modify: `agent-tools/telegram-bridge/src/telegram_bridge/permission_poller.py`

**Step 1: Add create_poller_task function**

Add a factory function that creates poller for specific session:

```python
# Add to permission_poller.py

async def create_poller_task(bot: Bot, session: SessionState) -> asyncio.Task:
    """Create permission poller task for session."""
    return asyncio.create_task(
        permission_poller_for_session(bot, session)
    )

async def permission_poller_for_session(bot: Bot, session: SessionState):
    """Poll for permissions in specific session."""
    from .tmux import TmuxSession

    tmux = TmuxSession(session.tmux_session, session.cwd)
    chat_id = session.chat_id

    # ... rest of poller logic, using tmux and chat_id instead of globals
```

The key change is parameterizing the poller with session info instead of using global settings.

**Step 2: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/permission_poller.py
git commit -m "refactor(telegram-bridge): parameterize permission_poller for multi-session"
```

---

### Task 9: Update watcher.py for multi-session

**Files:**
- Modify: `agent-tools/telegram-bridge/src/telegram_bridge/watcher.py`

**Step 1: Add create_watcher_task function**

Similar to poller - parameterize with session:

```python
# Add to watcher.py

async def create_watcher_task(bot: Bot, session: SessionState) -> asyncio.Task:
    """Create watcher task for session."""
    return asyncio.create_task(
        watcher_for_session(bot, session)
    )

async def watcher_for_session(bot: Bot, session: SessionState):
    """Watch jsonl for specific session."""
    path = Path(session.jsonl_path)
    chat_id = session.chat_id

    # ... rest of watcher logic using path and chat_id
```

**Step 2: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/watcher.py
git commit -m "refactor(telegram-bridge): parameterize watcher for multi-session"
```

---

### Task 10: Update .env

**Files:**
- Modify: `agent-tools/telegram-bridge/.env`

**Step 1: Update .env file**

Rename CHAT_ID to ADMIN_CHAT_ID, add BASE_DIR:

```bash
TELEGRAM_TOKEN=<existing token>
ADMIN_CHAT_ID=<your personal chat id>
BASE_DIR=/home/superbereza/dev
```

**Step 2: No commit (gitignored)**

---

### Task 11: Configure Claude hooks

**Files:**
- Modify: `~/.claude/settings.json`

**Step 1: Add hooks configuration**

```json
{
  "enabledPlugins": {
    "superpowers@superpowers-marketplace": true
  },
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/home/superbereza/dev/personal-agent/agent-tools/telegram-bridge/hooks/session-start.sh"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/home/superbereza/dev/personal-agent/agent-tools/telegram-bridge/hooks/session-end.sh"
          }
        ]
      }
    ]
  }
}
```

**Step 2: Test hooks**

Start new Claude session and verify HTTP request arrives at bot.

---

### Task 12: Integration test

**Step 1: Restart bot**

```bash
./restart.sh
```

**Step 2: Create Telegram group "personal-agent"**

Add bot to group.

**Step 3: Start new Claude session**

Should auto-register via hook.

**Step 4: Verify permission prompts appear in group**

Test with a tool that requires permission.
