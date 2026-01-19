# Group Authorization Design

## Что делаем

Разрешаем использование бота в группах, где хотя бы один админ группы есть в ADMIN_IDS. Не нужно добавлять каждого юзера в .env — достаточно чтобы админ из ADMIN_IDS создал группу.

## Правила авторизации

| Контекст | Кто может использовать |
|----------|------------------------|
| Личка (private) | Только ADMIN_IDS |
| Группа с админом из ADMIN_IDS | Любой участник группы |
| Группа без админа из ADMIN_IDS | Никто |
| Файлы/медиа в группе | Игнорируются (только текст) |

## Event-driven подход

Никакого polling или TTL-кэша. Всё через события:

1. **Бота добавили в группу** (`my_chat_member`) → проверяем админов → если есть наш → `allowed_groups.add(chat_id)`
2. **Первое сообщение в незнакомой группе** → аналогично
3. **Админ покинул группу** (`chat_member`) → перепроверяем → если админов из ADMIN_IDS не осталось → `allowed_groups.remove(chat_id)`

**Требование:** бот должен быть админом группы для получения событий `chat_member`. Это уже реализовано — бот просит админские права.

## Компоненты

| Файл | Назначение |
|------|------------|
| `services/group_auth.py` | GroupAuthService — бизнес-логика авторизации |
| `handlers/members.py` | Handler на ChatMemberUpdated (уход участников) |
| `middleware/admin.py` | Изменения в AdminMiddleware |
| `config.py` | Новые функции для allowed_groups |
| `strings.py` | Новые строки |

## GroupAuthService

```python
# src/codogram/services/group_auth.py

class GroupAuthService:
    """Manages group authorization based on admin membership."""

    def is_allowed(self, chat_id: int) -> bool:
        """Check if group is in allowed_groups."""

    async def check_and_register(self, bot: Bot, chat_id: int) -> bool:
        """Check group admins, register if valid.

        Returns True if group was registered (or already was).
        Returns False if no admin from ADMIN_IDS found.
        """

    async def on_admin_left(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        """Handle admin leaving group.

        If user_id in ADMIN_IDS, re-check group.
        Returns True if group was deactivated.
        """
```

## Handler для member events

```python
# handlers/members.py

"""Handler for member join/leave events."""
from aiogram import Router
from aiogram.types import ChatMemberUpdated

from ..services.group_auth import GroupAuthService
from ..telegram_queue import TelegramQueue
from .. import strings

router = Router(name="members")


@router.chat_member()
async def on_member_update(
    event: ChatMemberUpdated,
    telegram_queue: TelegramQueue,
    group_auth: GroupAuthService,
) -> None:
    """Handle member leaving group.

    If admin from ADMIN_IDS left — re-check group validity.
    """
    if not _is_leave(event):
        return

    deactivated = await group_auth.on_admin_left(
        event.bot, event.chat.id, event.from_user.id
    )

    if deactivated:
        await telegram_queue.send(
            event.chat.id, strings.GROUP_DEACTIVATED
        )


def _is_leave(event: ChatMemberUpdated) -> bool:
    """Check if user left or was kicked."""
    return event.new_chat_member.status in ("left", "kicked")
```

## Изменения в AdminMiddleware

```python
# middleware/admin.py

class AdminMiddleware(BaseMiddleware):
    def __init__(self, group_auth: GroupAuthService):
        self.group_auth = group_auth

    async def __call__(self, handler, event, data) -> Any:
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return None

        chat = data.get("event_chat")

        # Private chat — only ADMIN_IDS
        if chat is None or chat.type == "private":
            if is_admin(user.id):
                return await handler(event, data)
            await self._reject_non_admin(event, user.id, data)
            return None

        # Group/supergroup — check allowed_groups
        if chat.type in ("group", "supergroup"):
            # Ignore non-text messages (files, media)
            if isinstance(event, Message) and not event.text:
                return None

            # Check if group is allowed
            if self.group_auth.is_allowed(chat.id):
                return await handler(event, data)

            # First contact — try to register
            registered = await self.group_auth.check_and_register(
                data["bot"], chat.id
            )
            if registered:
                return await handler(event, data)

            # No admin from ADMIN_IDS in group
            await self._reject_group(event, data)
            return None

        return None

    async def _reject_group(self, event, data):
        """Send rejection for unauthorized group."""
        if isinstance(event, Message):
            telegram_queue = data["telegram_queue"]
            await telegram_queue.reply(event, strings.ERR_GROUP_NOT_ALLOWED)
```

## Изменения в config

**config.json** (новое поле):
```json
{
  "projects": {...},
  "allowed_groups": [123456789, 987654321]
}
```

**config.py** (новые функции):
```python
def get_allowed_groups() -> set[int]:
    """Get set of allowed group IDs."""
    config = load_config()
    return set(config.get("allowed_groups", []))

def add_allowed_group(group_id: int) -> None:
    """Add group to allowed list."""
    config = load_config()
    groups = set(config.get("allowed_groups", []))
    groups.add(group_id)
    config["allowed_groups"] = list(groups)
    save_config(config)

def remove_allowed_group(group_id: int) -> None:
    """Remove group from allowed list."""
    config = load_config()
    groups = set(config.get("allowed_groups", []))
    groups.discard(group_id)
    config["allowed_groups"] = list(groups)
    save_config(config)
```

## Новые строки (strings.py)

```python
# --- Group Authorization ---

ERR_GROUP_NOT_ALLOWED = f"{STATUS_ERR} Bot not active in this group"
GROUP_REGISTERED = f"{STATUS_OK} Group registered"
GROUP_DEACTIVATED = f"{STATUS_WARN} Admin left\\. Bot deactivated"
```

## Flow диаграмма

```
Сообщение приходит
        │
        ▼
   chat.type?
    /        \
private      group/supergroup
   │              │
   ▼              ▼
user_id in    text message?
ADMIN_IDS?        │
   │          no → ignore
  yes → OK        │
   │             yes
  no → reject     │
                  ▼
         group_id in allowed_groups?
              /            \
            yes             no
             │               │
             ▼               ▼
            OK        check_and_register()
                           │
                     есть админ из ADMIN_IDS?
                      /            \
                    yes             no
                     │               │
                     ▼               ▼
              add to allowed    reject
                     │
                     ▼
                    OK
```

## Регистрация в main.py

```python
# Создаём сервис
group_auth = GroupAuthService()

# Передаём в middleware
dp.message.middleware(AdminMiddleware(group_auth))
dp.callback_query.middleware(AdminMiddleware(group_auth))

# Регистрируем handler для chat_member events
from handlers import members
dp.include_router(members.router)
```
