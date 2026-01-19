# Migration Admin Rights Handling

## Problem

При миграции group → supergroup:
1. Telegram меняет chat_id
2. Отправляет два независимых события (порядок не гарантирован):
   - `migrate_to_chat_id` (MESSAGE в старом чате)
   - `my_chat_member` (ChatMemberUpdated в новом чате)
3. Права бота могут сброситься

**Текущие баги:**
- Если `my_chat_member` придёт раньше — запускается setup flow заново
- Emoji pack создаётся без проверки прав
- Вся функциональность работает без прав → ошибки API

## Solution

Добавить флаг `awaiting_admin_rights` в ProjectState и middleware для блокировки.

### Data Model Changes

```python
@dataclass
class ProjectState:
    ...
    old_chat_id: int | None = None      # Для детекции миграции
    awaiting_admin_rights: bool = False  # Блокировка до получения прав
```

### Middleware Stack

```
1. AdminMiddleware (user_id check)
2. BotAdminRightsMiddleware (NEW - bot permissions check)
3. ClearCreateStateMiddleware
4. SetupBlockerMiddleware
```

## Implementation

### 1. migration.py

При миграции:
```python
project.old_chat_id = old_chat_id
project.chat_id = new_chat_id

has_rights = await check_bot_admin_rights(bot, new_chat_id)
if not has_rights:
    project.awaiting_admin_rights = True
    # Показать сообщение, НЕ создавать emoji pack
else:
    # Создать emoji pack только если есть права
```

### 2. triggers.py — on_bot_added

Детектировать миграцию по old_chat_id:
```python
def _find_project_by_old_chat_id(chat_id: int) -> ProjectState | None:
    for project in project_manager.projects.values():
        if project.old_chat_id == chat_id:
            return project
    return None

async def on_bot_added(event, state):
    project = _find_project_by_old_chat_id(event.chat.id)
    if project:
        # Это миграция, НЕ запускать setup
        if project.chat_id != event.chat.id:
            project.chat_id = event.chat.id

        has_rights = await check_bot_admin_rights(...)
        if not has_rights:
            project.awaiting_admin_rights = True
            await send_admin_required_message(...)
        return

    # Обычный setup flow...
```

### 3. middleware/bot_admin_rights.py (NEW)

```python
class BotAdminRightsMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        chat_id = _get_chat_id(event)
        if not chat_id:
            return await handler(event, data)

        project = project_manager.get_by_chat(chat_id)
        if not project or not project.awaiting_admin_rights:
            return await handler(event, data)

        # Может права уже есть?
        bot = data.get("bot")
        has_rights = await check_bot_admin_rights(bot, chat_id)
        if has_rights:
            project.awaiting_admin_rights = False
            project_manager._save()
            return await handler(event, data)

        # Нет прав — заблокировать
        await _send_admin_required(event, data)
        return None
```

### 4. Handler для получения прав

```python
@router.my_chat_member(F.new_chat_member.status == "administrator")
async def on_bot_granted_admin(event: ChatMemberUpdated, telegram_queue):
    project = project_manager.get_by_chat(event.chat.id)
    if project and project.awaiting_admin_rights:
        project.awaiting_admin_rights = False
        project_manager._save()

        # Показать подтверждение
        await telegram_queue.send(event.chat.id, ADMIN_RIGHTS_GRANTED)

        # Теперь можно создать emoji pack
        asyncio.create_task(_create_emoji_pack_background(...))
```

## Messages (tone-of-voice)

**Запрос прав после миграции:**
```
`[!]` Admin rights required

Bot needs admin rights to manage topics.

Open chat settings → Administrators → Add bot
```

**Права получены:**
```
`[v]` Admin rights granted
```

## Files to Modify

| File | Change |
|------|--------|
| `session_manager.py` | Add `old_chat_id`, `awaiting_admin_rights` fields |
| `handlers/migration.py` | Save old_chat_id, check rights before emoji pack |
| `handlers/setup/triggers.py` | Detect migration by old_chat_id |
| `middleware/bot_admin_rights.py` | **NEW** — block if awaiting rights |
| `main.py` | Register new middleware |
| `strings.py` | Add messages |

## Edge Cases

| Case | Behavior |
|------|----------|
| `my_chat_member` arrives before `migrate_to_chat_id` | Detect by old_chat_id, don't start setup |
| Rights revoked manually (no migration) | Middleware sets flag on next API error |
| Bot restarted while awaiting rights | Flag persisted in config |
| Rights granted back | Handler clears flag, creates emoji pack |
| Migration without losing rights | Flag not set, everything works |

## Order of Events

**Happy path (migration + rights lost):**
1. `migrate_to_chat_id` → update chat_id, check rights → set flag
2. `my_chat_member` → detect migration, already flagged
3. User grants admin → `my_chat_member status=administrator` → clear flag

**Race condition (my_chat_member first):**
1. `my_chat_member` → find by old_chat_id fails (not set yet)
2. Check if supergroup + no project → wait 2s or proceed carefully
3. `migrate_to_chat_id` → update chat_id, set old_chat_id, check rights

## Race Condition Mitigation

В `on_bot_added`, если supergroup без проекта - две проверки:

### 1. Проверка по chat.title

```python
def _find_project_by_title(title: str) -> ProjectState | None:
    """Find project where project_name matches chat title."""
    for project in project_manager.projects.values():
        if project.project_name == title:
            return project
    return None
```

### 2. Delay fallback

Если по title не нашли - подождать 2s и перепроверить по chat_id.

### Полный flow

```python
async def on_bot_added(event, state):
    # ... existing checks ...

    # Check if project already registered by chat_id
    if _is_project_registered(chat.id):
        return

    # Race condition protection for migration (supergroups only)
    if chat.type == "supergroup":
        # 1. Check by title
        project = _find_project_by_title(chat.title)
        if project:
            logger.info(f"Migration detected by title: {chat.title}")
            project.old_chat_id = project.chat_id
            project.chat_id = chat.id
            # Check admin rights...
            return

        # 2. Delay fallback - wait for migrate_to_chat_id event
        await asyncio.sleep(2)
        if _is_project_registered(chat.id):
            logger.info(f"Migration detected after delay for chat {chat.id}")
            return

    await _start_setup_flow(...)
```
