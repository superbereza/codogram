# Group → Supergroup Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Handle chat_id change when topics are enabled, with scope-based menu registration.

**Architecture:** New `services/menu.py` for menu constants and registration. New `handlers/migration.py` for migration event. Fix `permission_poller.py` to read chat_id dynamically.

**Tech Stack:** aiogram 3.x, Python 3.11+

---

## Task 1: Create Menu Service

**Files:**
- Create: `src/codogram/services/menu.py`
- Create: `tests/test_menu_service.py`

**Step 1: Write the failing test**

```python
# tests/test_menu_service.py
import pytest
from codogram.services.menu import BASIC_COMMANDS, FORUM_COMMANDS, register_menu_for_chat


def test_basic_commands_count():
    """Basic menu has 9 commands (no /branch, /finish)."""
    assert len(BASIC_COMMANDS) == 9


def test_forum_commands_count():
    """Forum menu has 11 commands (includes /branch, /finish)."""
    assert len(FORUM_COMMANDS) == 11


def test_basic_commands_order():
    """Basic commands follow the defined order."""
    commands = [c.command for c in BASIC_COMMANDS]
    assert commands == [
        "esc", "auto_accept", "thread", "clear",
        "start", "settings", "restart", "get_debug_ids", "help"
    ]


def test_forum_commands_order():
    """Forum commands follow the defined order with branch/finish."""
    commands = [c.command for c in FORUM_COMMANDS]
    assert commands == [
        "esc", "auto_accept", "thread", "branch", "clear", "finish",
        "start", "settings", "restart", "get_debug_ids", "help"
    ]


def test_basic_excludes_branch_finish():
    """Basic menu does not include /branch and /finish."""
    commands = [c.command for c in BASIC_COMMANDS]
    assert "branch" not in commands
    assert "finish" not in commands


def test_forum_includes_branch_finish():
    """Forum menu includes /branch and /finish."""
    commands = [c.command for c in FORUM_COMMANDS]
    assert "branch" in commands
    assert "finish" in commands


def test_register_menu_for_chat_callable():
    """register_menu_for_chat should be async callable."""
    import asyncio
    assert asyncio.iscoroutinefunction(register_menu_for_chat)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_menu_service.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'codogram.services.menu'"

**Step 3: Write minimal implementation**

```python
# src/codogram/services/menu.py
"""Menu registration service for scope-based bot commands."""
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat

BASIC_COMMANDS = [
    BotCommand(command="esc", description="Cancel current operation"),
    BotCommand(command="auto_accept", description="Toggle auto-accept mode"),
    BotCommand(command="thread", description="New topic in project directory"),
    BotCommand(command="clear", description="Clear context, start fresh"),
    BotCommand(command="start", description="Connect Claude or show status"),
    BotCommand(command="settings", description="View current settings"),
    BotCommand(command="restart", description="Force restart Claude"),
    BotCommand(command="get_debug_ids", description="Show chat and thread IDs"),
    BotCommand(command="help", description="List all commands"),
]

FORUM_COMMANDS = [
    BotCommand(command="esc", description="Cancel current operation"),
    BotCommand(command="auto_accept", description="Toggle auto-accept mode"),
    BotCommand(command="thread", description="New topic in project directory"),
    BotCommand(command="branch", description="New isolated feature branch + topic"),
    BotCommand(command="clear", description="Clear context, start fresh"),
    BotCommand(command="finish", description="Merge branch, archive topic"),
    BotCommand(command="start", description="Connect Claude or show status"),
    BotCommand(command="settings", description="View current settings"),
    BotCommand(command="restart", description="Force restart Claude"),
    BotCommand(command="get_debug_ids", description="Show chat and thread IDs"),
    BotCommand(command="help", description="List all commands"),
]


async def register_menu_for_chat(bot: Bot, chat_id: int, is_forum: bool) -> None:
    """Register scope-based menu for a specific chat.

    Args:
        bot: Telegram bot instance
        chat_id: Target chat ID
        is_forum: True for forum (supergroup with topics), False for regular group
    """
    commands = FORUM_COMMANDS if is_forum else BASIC_COMMANDS
    scope = BotCommandScopeChat(chat_id=chat_id)
    await bot.set_my_commands(commands, scope=scope)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_menu_service.py -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add src/codogram/services/menu.py tests/test_menu_service.py
git commit -m "feat: add menu service with scope-based commands"
```

---

## Task 2: Create Migration Handler

**Files:**
- Create: `src/codogram/handlers/migration.py`
- Create: `tests/test_migration_handler.py`

**Step 1: Write the failing test**

```python
# tests/test_migration_handler.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from codogram.handlers.migration import router, on_chat_migration, MIGRATION_MESSAGE


def test_router_exists():
    """Migration router should exist."""
    assert router is not None
    assert router.name == "migration"


def test_migration_message_format():
    """Migration message follows tone-of-voice."""
    assert "`[v]` Topics enabled" in MIGRATION_MESSAGE
    assert "/thread" in MIGRATION_MESSAGE
    assert "/branch" in MIGRATION_MESSAGE
    assert "/finish" in MIGRATION_MESSAGE


@pytest.mark.asyncio
async def test_migration_ignores_unknown_chat():
    """Migration handler ignores chats without registered project."""
    from codogram.session_manager import project_manager

    message = MagicMock()
    message.chat.id = 999999
    message.migrate_to_chat_id = 888888

    telegram_queue = AsyncMock()

    with patch.object(project_manager, 'get_by_chat', return_value=None):
        await on_chat_migration(message, telegram_queue)

    # Should not send any message
    telegram_queue.enqueue.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_migration_handler.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'codogram.handlers.migration'"

**Step 3: Write minimal implementation**

```python
# src/codogram/handlers/migration.py
"""Handler for group → supergroup migration event."""
from aiogram import Router, F
from aiogram.types import Message

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue, OutgoingBatch
from ..services.menu import register_menu_for_chat
from ..logging_config import logger

router = Router(name="migration")

MIGRATION_MESSAGE = """`[v]` Topics enabled

Multi-session mode unlocked:
/thread — new topic, same directory
/branch — isolated feature branch + topic
/finish — merge and archive"""


@router.message(F.migrate_to_chat_id)
async def on_chat_migration(message: Message, telegram_queue: TelegramQueue) -> None:
    """Handle chat migration when topics are enabled.

    Telegram changes chat_id when converting group to supergroup (forum).
    This handler updates the project's chat_id and registers extended menu.
    """
    old_chat_id = message.chat.id
    new_chat_id = message.migrate_to_chat_id

    logger.info(f"migration_detected: old={old_chat_id} new={new_chat_id}")

    # Find project by old chat_id
    project = project_manager.get_by_chat(old_chat_id)
    if not project:
        logger.debug(f"migration_ignored: no project for chat={old_chat_id}")
        return

    # Update chat_id
    project.chat_id = new_chat_id
    project_manager._save()
    logger.info(f"migration_updated: project={project.project_name} new_chat_id={new_chat_id}")

    # Register extended menu for forum
    await register_menu_for_chat(message.bot, new_chat_id, is_forum=True)

    # Send notification
    batch = OutgoingBatch(
        chat_id=new_chat_id,
        thread_id=None,
        messages=[{"text": MIGRATION_MESSAGE}],
    )
    await telegram_queue.enqueue(batch)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_migration_handler.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/codogram/handlers/migration.py tests/test_migration_handler.py
git commit -m "feat: add migration handler for group→supergroup"
```

---

## Task 3: Register Migration Router

**Files:**
- Modify: `src/codogram/handlers/__init__.py:4,18`

**Step 1: Write the failing test**

```python
# Add to existing tests or run integration check
# tests/test_handlers_init.py (if exists) or just verify import works
```

For this simple change, we verify by import:

```bash
python -c "from codogram.handlers import migration; print('OK')"
```

Expected: OK (after implementation)

**Step 2: Modify handlers/__init__.py**

Add import at line 4:
```python
from . import permissions, start, threads, branches, sessions, settings, finish, common, messages, migration
```

Add router registration after line 18 (before permissions):
```python
    dp.include_router(migration.router)    # Migration events (must be early)
    dp.include_router(permissions.router)   # Permission callbacks
```

**Step 3: Verify import works**

Run: `python -c "from codogram.handlers import migration; print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add src/codogram/handlers/__init__.py
git commit -m "feat: register migration router in handlers"
```

---

## Task 4: Update main.py to Use Menu Service

**Files:**
- Modify: `src/codogram/main.py:42-55`

**Step 1: Identify current code**

Current code at lines 42-55:
```python
from aiogram.types import BotCommand
await bot.set_my_commands([
    BotCommand(command="esc", description="Cancel current operation"),
    ...
])
```

**Step 2: Replace with menu service import**

```python
from .services.menu import BASIC_COMMANDS

# ... later in main() ...

# Set global default menu (for new chats)
await bot.set_my_commands(BASIC_COMMANDS)
```

**Step 3: Run bot to verify**

Run: `./restart.sh && sleep 3 && ps aux | grep codogram`
Expected: Bot running

**Step 4: Commit**

```bash
git add src/codogram/main.py
git commit -m "refactor: use menu service for global commands"
```

---

## Task 5: Add Menu Registration to Start Handler

**Files:**
- Modify: `src/codogram/handlers/start.py`
- Modify: `tests/test_handlers_start.py` (if exists)

**Step 1: Identify insertion point**

After successful project registration in `cmd_start` (around line 385) and in `_launch_claude` helpers.

Best place: after `_handle_result` when result.action is CONNECT or LAUNCH.

Actually, simpler: add to `_launch_claude` and `_connect_to_session` after project is confirmed.

**Step 2: Add import at top of file**

```python
from ..services.menu import register_menu_for_chat
```

**Step 3: Add menu registration after project registration**

In `_connect_to_session` (around line 348), after `project_manager._save()`:
```python
async def _connect_to_session(message: Message, result: FlowResult, telegram_queue: TelegramQueue):
    """Connect to existing tmux session."""
    project = project_manager.get_by_chat(message.chat.id)
    if project:
        project.tmux_session = result.tmux_session
        project_manager._save()

        # Register menu based on chat type
        await register_menu_for_chat(
            message.bot,
            message.chat.id,
            is_forum=message.chat.is_forum or False
        )

        await telegram_queue.reply(
            message,
            f"Connected to `{result.tmux_session}`",
        )
```

Similar change in `_launch_claude` after getting project.

**Step 4: Run tests**

Run: `pytest tests/test_handlers_start.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/start.py
git commit -m "feat: register scope-based menu on /start"
```

---

## Task 6: Fix Permission Poller Dynamic chat_id

**Files:**
- Modify: `src/codogram/permission_poller.py:115,142-144,203-206,232-241,249-260,275-276`
- Modify: `tests/test_permission_poller.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_permission_poller.py
def test_permission_poller_no_cached_chat_id():
    """permission_poller should not cache chat_id at function start."""
    import ast
    from pathlib import Path

    # Read source file
    source = Path("src/codogram/permission_poller.py").read_text()
    tree = ast.parse(source)

    # Find permission_poller function
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "permission_poller":
            # Get first 20 lines of function body
            func_source = ast.get_source_segment(source, node)
            first_lines = "\n".join(func_source.split("\n")[:30])

            # Should NOT have "chat_id = project.chat_id" as standalone assignment
            assert "chat_id = project.chat_id" not in first_lines, \
                "chat_id should not be cached at function start"
            break
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_permission_poller.py::test_permission_poller_no_cached_chat_id -v`
Expected: FAIL (chat_id is currently cached at line 115)

**Step 3: Fix permission_poller.py**

Remove line 115:
```python
# DELETE: chat_id = project.chat_id
```

Replace all uses of `chat_id` with `project.chat_id`:

Line 142-144 (crash detection):
```python
batch = OutgoingBatch(
    chat_id=project.chat_id,  # was: chat_id
    thread_id=thread_id,
```

Line 203-206:
```python
batch = OutgoingBatch(
    chat_id=project.chat_id,  # was: chat_id
    thread_id=thread_id,
```

Line 211-217:
```python
kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch(
    chat_id=project.chat_id,  # was: chat_id
    text="👆",
```

Line 232-241 (cleanup):
```python
await bot.delete_message(project.chat_id, msg_id)  # was: chat_id
...
await bot.delete_message(project.chat_id, kb_msg_id)  # was: chat_id
```

Line 253-260:
```python
await bot.delete_message(project.chat_id, msg_id)  # was: chat_id
...
await bot.delete_message(project.chat_id, kb_msg_id)  # was: chat_id
```

Line 275:
```python
batch = OutgoingBatch(chat_id=project.chat_id, thread_id=thread_id, messages=body_messages)
```

Line 280-284:
```python
kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch(
    chat_id=project.chat_id,  # was: chat_id
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_permission_poller.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/permission_poller.py tests/test_permission_poller.py
git commit -m "fix: use dynamic project.chat_id in permission_poller"
```

---

## Task 7: Add E2E Test Cases

**Files:**
- Modify: `docs/e2e/commands/start.md`

**Step 1: Add test cases to start.md**

Append to `docs/e2e/commands/start.md`:

```markdown
---

## TC-START-008: /start in forum registers extended menu

**Tags:** critical, start, menu
**Preconditions:** Supergroup with topics enabled

**Steps:**
```python
mcp__telegram__send_message(chat_id=FORUM_CHAT_ID, message="/start")
# Wait 5s
```

**Expected:**
- ASK USER: "Can you see /branch and /finish in bot menu?"

---

## TC-START-009: /start in regular group registers basic menu

**Tags:** critical, start, menu
**Preconditions:** Regular group (not forum)

**Steps:**
```python
mcp__telegram__send_message(chat_id=REGULAR_GROUP_ID, message="/start")
# Wait 5s
```

**Expected:**
- ASK USER: "Confirm that /branch and /finish are NOT in bot menu"

---

## TC-START-010: Migration updates chat_id

**Tags:** critical, start, migration
**Preconditions:** Bot registered in regular group, active session

**Setup:**
```bash
cat .config.json | jq '.projects["<project>"].chat_id'
# Note current chat_id
```

**Human action required:**
ASK USER: "Please enable Topics in the test group:
Settings → Topics → Enable. Let me know when done."

**Steps:**
1. After user confirms, wait 5s
2. Check new chat_id:
```bash
cat .config.json | jq '.projects["<project>"].chat_id'
```
3. Read messages in NEW chat:
```python
mcp__telegram__list_messages(chat_id=NEW_CHAT_ID, limit=5)
```

**Expected:**
- chat_id changed in config
- Notification: "[v] Topics enabled..." in new chat
- ASK USER: "Can you see /branch and /finish in bot menu?"

---

## TC-START-011: Permission poller works after migration

**Tags:** critical, start, migration, permissions
**Preconditions:** TC-START-010 completed, Claude running

**Steps:**
```python
mcp__telegram__send_message(chat_id=NEW_CHAT_ID, message="run ls /")
# Wait 10s
mcp__telegram__list_inline_buttons(chat_id=NEW_CHAT_ID)
```

**Expected:**
- Permission prompt with Yes/No buttons in NEW chat

---

## TC-START-012: Watcher works after migration

**Tags:** critical, start, migration, watcher
**Preconditions:** TC-START-010 completed, Claude running

**Steps:**
1. Accept pending permission if any
```python
mcp__telegram__send_message(chat_id=NEW_CHAT_ID, message="read README.md")
# Wait 15s
mcp__telegram__list_messages(chat_id=NEW_CHAT_ID, limit=10)
```

**Expected:**
- Tool call notification (● Read...) in NEW chat
```

**Step 2: Commit**

```bash
git add docs/e2e/commands/start.md
git commit -m "docs: add E2E tests for migration feature"
```

---

## Task 8: Final Verification

**Step 1: Run all tests**

```bash
pytest -v
```

Expected: All tests PASS

**Step 2: Run bot and verify manually**

```bash
./restart.sh
```

Check logs for any errors.

**Step 3: Final commit (if any fixes needed)**

```bash
git status
# If clean, done. Otherwise fix and commit.
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Menu service | services/menu.py, tests/test_menu_service.py |
| 2 | Migration handler | handlers/migration.py, tests/test_migration_handler.py |
| 3 | Register router | handlers/__init__.py |
| 4 | Update main.py | main.py |
| 5 | Menu on /start | handlers/start.py |
| 6 | Fix poller chat_id | permission_poller.py, tests/test_permission_poller.py |
| 7 | E2E tests | docs/e2e/commands/start.md |
| 8 | Verification | — |

Total: ~8 tasks, ~45 minutes estimated
