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

## Event-driven подход + persistence

**Persistence:** `allowed_groups` хранится в config.json для быстрой проверки без API вызовов.

**Re-validate:** При первом сообщении после рестарта бота — делаем API вызов чтобы актуализировать данные (вдруг админ ушёл пока бот лежал).

**События:**

1. **Бота добавили в группу** (`my_chat_member`) → проверяем админов → если есть наш → `allowed_groups.add(chat_id)`
2. **Бота удалили из группы** (`my_chat_member`) → `allowed_groups.remove(chat_id)`
3. **Первое сообщение в незнакомой группе** → проверяем админов → регистрируем если ок
4. **Первое сообщение после рестарта** → re-validate группу
5. **Админ покинул/понижен** (`chat_member`) → перепроверяем → если админов из ADMIN_IDS не осталось → `allowed_groups.remove(chat_id)`

**Требование:** бот должен быть админом группы для получения событий `chat_member`. Это уже реализовано — бот просит админские права.

**Known limitation:** Если бот не админ, события об уходе участников не получит. Но бот требует админские права для работы, так что это не проблема.

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

    def __init__(self):
        self._checking: set[int] = set()  # Groups being checked (race condition protection)
        self._validated_this_run: set[int] = set()  # Groups re-validated after restart

    def is_allowed(self, chat_id: int) -> bool:
        """Check if group is in allowed_groups."""

    def needs_revalidation(self, chat_id: int) -> bool:
        """Check if group needs re-validation (first message after restart)."""
        return chat_id in get_allowed_groups() and chat_id not in self._validated_this_run

    async def check_and_register(self, bot: Bot, chat_id: int) -> bool:
        """Check group admins, register if valid.

        Returns True if group was registered (or already was).
        Returns False if no admin from ADMIN_IDS found.

        Race condition protection: if already checking this group, returns False.
        """
        if chat_id in self._checking:
            return False  # Already checking, avoid duplicate API calls

        self._checking.add(chat_id)
        try:
            # ... actual check via getChatAdministrators
            # ... if valid: add_allowed_group(chat_id)
            self._validated_this_run.add(chat_id)
            return result
        finally:
            self._checking.discard(chat_id)

    async def revalidate(self, bot: Bot, chat_id: int) -> bool:
        """Re-validate group after restart.

        Returns True if still valid, False if deactivated.
        """
        self._validated_this_run.add(chat_id)
        # ... check admins, remove if no longer valid

    async def on_admin_left(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        """Handle admin leaving or being demoted.

        If user_id in ADMIN_IDS, re-check group.
        Returns True if group was deactivated.
        """

    def on_bot_removed(self, chat_id: int) -> None:
        """Handle bot being removed from group."""
        remove_allowed_group(chat_id)
        self._validated_this_run.discard(chat_id)
```

## Handler для member events

```python
# handlers/members.py

"""Handler for member join/leave and bot status events."""
from aiogram import Router
from aiogram.types import ChatMemberUpdated

from ..services.group_auth import GroupAuthService
from ..telegram_queue import TelegramQueue
from ..logging_config import logger
from .. import strings

router = Router(name="members")


# --- Bot status events (my_chat_member) ---

@router.my_chat_member()
async def on_bot_status_changed(
    event: ChatMemberUpdated,
    group_auth: GroupAuthService,
) -> None:
    """Handle bot being added/removed from group."""
    chat_type = event.chat.type
    if chat_type not in ("group", "supergroup"):
        return

    new_status = event.new_chat_member.status

    if new_status in ("member", "administrator"):
        # Bot added to group — try to register
        logger.info(f"bot_added_to_group: chat_id={event.chat.id}")
        await group_auth.check_and_register(event.bot, event.chat.id)

    elif new_status in ("left", "kicked"):
        # Bot removed from group
        logger.info(f"bot_removed_from_group: chat_id={event.chat.id}")
        group_auth.on_bot_removed(event.chat.id)


# --- Member events (chat_member) ---

@router.chat_member()
async def on_member_update(
    event: ChatMemberUpdated,
    telegram_queue: TelegramQueue,
    group_auth: GroupAuthService,
) -> None:
    """Handle member leaving or being demoted.

    If admin from ADMIN_IDS left/demoted — re-check group validity.
    """
    if not _is_leave_or_demotion(event):
        return

    deactivated = await group_auth.on_admin_left(
        event.bot, event.chat.id, event.from_user.id
    )

    if deactivated:
        logger.info(f"group_deactivated: chat_id={event.chat.id}")
        await telegram_queue.send(
            event.chat.id, strings.GROUP_DEACTIVATED
        )


def _is_leave_or_demotion(event: ChatMemberUpdated) -> bool:
    """Check if user left, was kicked, or was demoted from admin."""
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    # Left or kicked
    if new_status in ("left", "kicked"):
        return True

    # Demoted from admin/creator to regular member
    old_is_admin = old_status in ("administrator", "creator")
    new_is_admin = new_status in ("administrator", "creator")
    if old_is_admin and not new_is_admin:
        return True

    return False
```

## Изменения в AdminMiddleware

```python
# middleware/admin.py

from aiogram.types import Message, CallbackQuery

class AdminMiddleware(BaseMiddleware):
    def __init__(self, group_auth: GroupAuthService):
        self.group_auth = group_auth

    async def __call__(self, handler, event, data) -> Any:
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return None

        chat = data.get("event_chat")

        # Unknown chat — ignore
        if chat is None:
            logger.debug("middleware_skip: chat is None")
            return None

        # Private chat — only ADMIN_IDS
        if chat.type == "private":
            if is_admin(user.id):
                return await handler(event, data)
            await self._reject_non_admin(event, user.id, data)
            return None

        # Group/supergroup — check allowed_groups
        if chat.type in ("group", "supergroup"):
            # Ignore non-text messages (files, media)
            if isinstance(event, Message) and not event.text:
                return None

            # Re-validate after restart if needed
            if self.group_auth.needs_revalidation(chat.id):
                logger.debug(f"revalidating_group: chat_id={chat.id}")
                valid = await self.group_auth.revalidate(data["bot"], chat.id)
                if not valid:
                    logger.info(f"group_invalidated_on_revalidation: chat_id={chat.id}")
                    await self._reject_group(event, data)
                    return None
                return await handler(event, data)

            # Check if group is allowed
            if self.group_auth.is_allowed(chat.id):
                return await handler(event, data)

            # First contact — try to register
            registered = await self.group_auth.check_and_register(
                data["bot"], chat.id
            )
            if registered:
                logger.info(f"group_registered: chat_id={chat.id}")
                return await handler(event, data)

            # No admin from ADMIN_IDS in group
            logger.debug(f"group_rejected: chat_id={chat.id}")
            await self._reject_group(event, data)
            return None

        # Unknown chat type — ignore
        return None

    async def _reject_group(self, event, data):
        """Send rejection for unauthorized group."""
        if isinstance(event, Message):
            telegram_queue = data["telegram_queue"]
            await telegram_queue.reply(event, strings.ERR_GROUP_NOT_ALLOWED)
        elif isinstance(event, CallbackQuery):
            await event.answer(
                strings.ERR_GROUP_NOT_ALLOWED_POPUP,
                show_alert=True
            )
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
ERR_GROUP_NOT_ALLOWED_POPUP = "[x] Bot not active in this group"  # Plain text for callback popup
GROUP_REGISTERED = f"{STATUS_OK} Group registered"
GROUP_DEACTIVATED = f"{STATUS_WARN} Admin left\\. Bot deactivated"
```

## Flow диаграмма

```
Сообщение приходит
        │
        ▼
   chat is None? ──yes──→ ignore
        │
        no
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
         needs_revalidation?
              /            \
            yes             no
             │               │
             ▼               ▼
        revalidate()   group_id in allowed_groups?
             │              /            \
        valid?            yes             no
         /   \             │               │
       yes    no           ▼               ▼
        │      │          OK        check_and_register()
        ▼      ▼                           │
       OK   reject               есть админ из ADMIN_IDS?
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

# Inject в aiogram DI
dp["group_auth"] = group_auth

# Передаём в middleware
dp.message.middleware(AdminMiddleware(group_auth))
dp.callback_query.middleware(AdminMiddleware(group_auth))

# Регистрируем handlers для chat_member events
from handlers import members
dp.include_router(members.router)

# ВАЖНО: для получения chat_member и my_chat_member событий
# нужно передать allowed_updates в start_polling:
await dp.start_polling(
    bot,
    allowed_updates=["message", "callback_query", "chat_member", "my_chat_member", ...]
)
```
