# Group → Supergroup Migration Design

## Overview

При включении топиков (Forum mode) в обычной группе Telegram автоматически конвертирует её в супергруппу, меняя `chat_id`. Текущее поведение — проект становится "сиротой", требуется повторный `/start`.

## Solution

1. **Слушать событие `migrate_to_chat_id`** — aiogram filter на `message.migrate_to_chat_id`
2. **Обновить `chat_id` в конфиге** — через `ProjectManager`
3. **Зарегистрировать расширенное меню** — `BotCommandScopeChat` с `/branch`, `/finish`
4. **Уведомить пользователя** — сообщение в стиле tone-of-voice

## Scope-based Menu

Два набора команд с сохранением текущего порядка:

**Базовый (группа без топиков):**
1. `/esc`
2. `/auto_accept`
3. `/thread`
4. `/clear`
5. `/start`
6. `/settings`
7. `/restart`
8. `/get_debug_ids`
9. `/help`

**Расширенный (супергруппа с топиками):**
1. `/esc`
2. `/auto_accept`
3. `/thread`
4. `/branch` ← добавлено
5. `/clear`
6. `/finish` ← добавлено
7. `/start`
8. `/settings`
9. `/restart`
10. `/get_debug_ids`
11. `/help`

## Trigger Points

1. **Migration event** — автоматически при включении топиков
2. **`/start` в новом чате** — проверка `chat.is_forum` при регистрации

## Architecture

### New Handler: `handlers/migration.py`

```python
from aiogram import Router, F
from aiogram.types import Message

router = Router()

@router.message(F.migrate_to_chat_id)
async def on_chat_migration(message: Message, telegram_queue: TelegramQueue):
    old_chat_id = message.chat.id
    new_chat_id = message.migrate_to_chat_id

    # 1. Find project by old chat_id
    project = project_manager.get_by_chat(old_chat_id)
    if not project:
        return  # Not our chat

    # 2. Update chat_id
    project.chat_id = new_chat_id
    project_manager._save()

    # 3. Register extended menu for this chat
    await register_forum_menu(message.bot, new_chat_id)

    # 4. Send notification
    await telegram_queue.enqueue(new_chat_id, None, MIGRATION_MESSAGE)
```

### Menu Registration: `services/menu.py`

```python
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

async def register_menu_for_chat(bot: Bot, chat_id: int, is_forum: bool):
    commands = FORUM_COMMANDS if is_forum else BASIC_COMMANDS
    scope = BotCommandScopeChat(chat_id=chat_id)
    await bot.set_my_commands(commands, scope=scope)
```

### Changes to `handlers/start.py`

При успешной регистрации проекта — проверить `chat.is_forum` и зарегистрировать нужное меню:

```python
async def on_start(message: Message, ...):
    # ... existing logic ...

    # After project registered successfully:
    await register_menu_for_chat(
        message.bot,
        message.chat.id,
        is_forum=message.chat.is_forum or False
    )
```

### Global Default Menu in `main.py`

Оставить базовое меню как глобальный fallback для новых чатов:

```python
await bot.set_my_commands(BASIC_COMMANDS)  # Global default
```

## Messages (per tone-of-voice.md)

**Migration notification:**
```
`[v]` Topics enabled

Multi-session mode unlocked:
/thread — new topic, same directory
/branch — isolated feature branch + topic
/finish — merge and archive
```

## Fix: Permission Poller Dynamic chat_id

### Problem

`permission_poller.py:115` кэширует `chat_id` при старте:
```python
chat_id = project.chat_id  # Cached once!
```

После миграции poller будет отправлять на старый chat_id.

### Solution

Читать `project.chat_id` динамически:

```python
# Было:
chat_id = project.chat_id
...
batch = OutgoingBatch(chat_id=chat_id, ...)

# Стало: убрать кэширование
batch = OutgoingBatch(chat_id=project.chat_id, ...)  # Dynamic read
```

**Note:** `watch_thread_jsonl` уже читает `project.chat_id` динамически — там ок.

## Files to Modify

| File | Change |
|------|--------|
| `handlers/__init__.py` | Add `migration.router` |
| `handlers/migration.py` | **NEW** — migration event handler |
| `services/menu.py` | **NEW** — menu registration logic |
| `handlers/start.py` | Call `register_menu_for_chat()` after registration |
| `main.py` | Use `BASIC_COMMANDS` as global default |
| `permission_poller.py` | Remove `chat_id` caching, use `project.chat_id` dynamically |

## E2E Tests

Добавить в `docs/e2e/commands/start.md`:

### TC-START-008: /start in forum registers extended menu
```
Tags: critical, start, menu
Preconditions: Supergroup with topics enabled
Steps: /start in forum chat
Expected: Menu includes /branch, /finish
```

### TC-START-009: /start in regular group registers basic menu
```
Tags: critical, start, menu
Preconditions: Regular group (not forum)
Steps: /start
Expected: Menu does NOT include /branch, /finish
```

### TC-START-010: Migration updates chat_id
```
Tags: critical, start, migration
Preconditions: Bot registered in regular group, active session

Setup:
1. Note current chat_id:
   cat .config.json | jq '.projects["<project>"].chat_id'

Human action required:
   ASK USER: "Please enable Topics in the test group:
   Settings → Topics → Enable. Let me know when done."

Steps:
1. After user confirms, wait 5s
2. Check new chat_id:
   cat .config.json | jq '.projects["<project>"].chat_id'
3. Read messages in NEW chat:
   mcp__telegram__list_messages(chat_id=NEW_CHAT_ID, limit=5)

Expected:
  - chat_id changed in config
  - Notification: "[v] Topics enabled..." in new chat
  - ASK USER: "Can you see /branch and /finish in bot menu?"
```

### TC-START-011: Permission poller works after migration
```
Tags: critical, start, migration, permissions
Preconditions: TC-START-010 completed, Claude running

Steps:
1. Send command that triggers permission:
   mcp__telegram__send_message(chat_id=NEW_CHAT_ID, message="run ls /")
2. Wait 10s
3. Check for permission buttons:
   mcp__telegram__list_inline_buttons(chat_id=NEW_CHAT_ID)

Expected:
  - Permission prompt with Yes/No buttons in NEW chat
  - NOT in old chat
```

### TC-START-012: Watcher works after migration
```
Tags: critical, start, migration, watcher
Preconditions: TC-START-010 completed, Claude running

Steps:
1. Accept pending permission if any
2. Send message that triggers tool call:
   mcp__telegram__send_message(chat_id=NEW_CHAT_ID, message="read README.md")
3. Wait 15s
4. Check messages:
   mcp__telegram__list_messages(chat_id=NEW_CHAT_ID, limit=10)

Expected:
  - Tool call notification (● Read...) in NEW chat
```

### Regression Tests

После реализации прогнать:
- `docs/e2e/suites/smoke.md`
- TC-START-001..007
- TC-THREAD-*
- TC-BRANCH-*
- TC-PERM-*
- TC-WATCH-*

## Edge Cases

| Case | Behavior |
|------|----------|
| Migration в неизвестном чате | Ignore (no project found) |
| Topics disabled после миграции | Меню остаётся расширенным (accepted) |
| Bot restarted after migration | Menu persists (per-chat scope) |
