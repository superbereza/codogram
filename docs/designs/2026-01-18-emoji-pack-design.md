# Custom Emoji Pack из аватарок участников

## Что делаем

При миграции группы → супергруппы бот создаёт emoji pack с аватарками всех участников. При входе/выходе участников — обновляет pack.

## UX Flow

### При миграции (автоматически)

1. Юзер включает Topics → migration event
2. Бот создаёт pack в фоне (async)
3. Готово → уведомление в General: "Gift unlocked..."
4. Фича `feat_avatar_pack` автоматически ON
5. Pack поддерживается при join/leave участников

### Команда `/exp_avatar_pack`

Сразу показывает prompt в зависимости от текущего состояния:

**Если ON:**
- "Disable avatar pack? Pack will be deleted."
- Кнопки: [Yes, disable] / [Keep it]

**Если OFF:**
- "Create avatar pack? Will generate emoji from member avatars."
- Кнопки: [Yes, create] / [Not now]

### В `/settings`

```
experimental features
• /exp_thinking_status: ○ off
• /exp_suggestions: ○ off
• /exp_avatar_pack: ● on
```

## Ограничения Telegram

- **Premium required** для установки custom emoji как иконки топика
- Pack может создать только реальный user (берём `ADMIN_IDS[0]`)
- Стандартные 112 emoji из `getForumTopicIconStickers` доступны всем

## Компоненты

| Файл | Назначение |
|------|------------|
| `services/emoji_pack.py` | Основная логика: create/add/remove/delete |
| `handlers/migration.py` | Триггер при включении topics |
| `handlers/members.py` | Триггер при join/leave |
| `handlers/settings.py` | Команда `/exp_avatar_pack` |
| `keyboards/avatar_pack.py` | Клавиатуры для create/disable prompts |
| `domain/project.py` | Поля `feat_avatar_pack`, `emoji_pack_name`, `emoji_map` |
| `strings.py` | Все сообщения для emoji pack |

## Структура сервиса

```python
class EmojiPackService:
    async def create_pack(self, chat_id: int, participants: list[User]) -> str:
        """Создать pack со всеми участниками. Возвращает pack name."""

    async def delete_pack(self, chat_id: int) -> None:
        """Удалить pack и очистить emoji_map."""

    async def add_member(self, chat_id: int, user: User) -> str:
        """Добавить аватарку участника. Возвращает custom_emoji_id."""

    async def remove_member(self, chat_id: int, user_id: int) -> None:
        """Удалить аватарку участника."""

    async def get_emoji_id(self, chat_id: int, user_id: int) -> str | None:
        """Получить custom_emoji_id по user_id."""

    # Private
    async def _download_avatar(self, user: User) -> bytes | None
    def _generate_placeholder(self, user: User) -> bytes
    def _process_image(self, image_bytes: bytes) -> bytes
    def _get_font(self, size: int) -> ImageFont.FreeTypeFont
```

## Хранение данных

В Project model:

```python
@dataclass
class Project:
    # ... existing fields ...
    feat_avatar_pack: bool = False  # experimental feature toggle
    emoji_pack_name: str | None = None
    emoji_map: dict[int, str] = field(default_factory=dict)  # {user_id: custom_emoji_id}
```

Config.json:

```json
{
  "projects": {
    "codogram": {
      "feat_avatar_pack": true,
      "emoji_pack_name": "chat_3532995083_avatars_by_claudecode_assist_bot",
      "emoji_map": {
        "34185809": "5368324170671202286"
      }
    }
  }
}
```

## Обработка изображений

**Зависимости:** Pillow>=10.0.0

**Аватарка есть:**
1. `getUserProfilePhotos` → file_id
2. `getFile` + `downloadFile` → bytes
3. Resize 100x100, круглая маска → PNG bytes

**Аватарки нет — placeholder:**
1. Цвет по `user_id % 7` (Telegram colors)
2. Первая буква имени
3. Круг 100x100 с буквой по центру

```python
TELEGRAM_COLORS = [
    "#FF5733", "#33A1FF", "#8E44AD", "#27AE60",
    "#F39C12", "#E74C3C", "#1ABC9C"
]
```

Шрифт: системный DejaVuSans-Bold или fallback.

## Интеграция с handlers

**Migration** (`handlers/migration.py`):

```python
@router.message(F.migrate_to_chat_id)
async def on_chat_migration(message: Message, ...) -> None:
    # ... existing logic ...

    # Асинхронно, не блокируем
    asyncio.create_task(
        _create_emoji_pack_background(message.bot, new_chat_id)
    )
```

**Member events** (`handlers/members.py`):

```python
@router.chat_member()
async def on_member_update(event: ChatMemberUpdated) -> None:
    project = project_manager.get_by_chat(event.chat.id)
    if not project or not project.feat_avatar_pack:
        return

    if _is_join(event):
        await service.add_member(...)
    elif _is_leave(event):
        await service.remove_member(...)
```

**Command** (`handlers/settings.py`):

```python
@router.message(Command("exp_avatar_pack"))
async def cmd_exp_avatar_pack(message: Message, telegram_queue: TelegramQueue):
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    if project.feat_avatar_pack:
        # Показываем prompt на отключение
        kb = avatar_pack_disable_keyboard()
        await telegram_queue.reply(message, EMOJI_PACK_DISABLE_PROMPT, reply_markup=kb)
    else:
        # Показываем prompt на создание
        kb = avatar_pack_create_keyboard()
        await telegram_queue.reply(message, EMOJI_PACK_CREATE_PROMPT, reply_markup=kb)
```

## Error handling

| Ситуация | Решение |
|----------|---------|
| Pack уже существует | Пропускаем создание |
| Юзер уже в pack'е | Проверяем `emoji_map` |
| Юзер не в pack'е при удалении | Warning, не падаем |
| Бот не админ | Ловим ошибку, логируем |
| Rate limit | `sleep(0.5)` между добавлениями |

## Конфигурация

**Owner для sticker set:**

```python
# config.py
@property
def bot_owner_id(self) -> int:
    return self.admin_ids[0]
```

**Pack naming:**

```
chat_{chat_id}_avatars_by_{bot_username}
```

## Сообщения (strings.py)

```python
# После создания pack'а (миграция или команда)
EMOJI_PACK_CREATED = """`[v]` Gift unlocked

Avatar pack — set members as topic icons: {pack_link}

*(requires Premium)*"""

# /exp_avatar_pack когда ON
EMOJI_PACK_DISABLE_PROMPT = """`[?]` Disable avatar pack?

Pack will be deleted."""
EMOJI_PACK_BTN_DISABLE = "Yes, disable"
EMOJI_PACK_BTN_KEEP = "Keep it"

# /exp_avatar_pack когда OFF
EMOJI_PACK_CREATE_PROMPT = """`[?]` Create avatar pack?

Will generate emoji from member avatars."""
EMOJI_PACK_BTN_CREATE = "Yes, create"
EMOJI_PACK_BTN_NOT_NOW = "Not now"

# После удаления
EMOJI_PACK_DELETED = "`[v]` Avatar pack disabled"

# Во время создания (опционально)
EMOJI_PACK_CREATING = "`[~]` Creating avatar pack..."
```

## API методы Telegram

- `createNewStickerSet` — создать pack (`sticker_type="custom_emoji"`)
- `addStickerToSet` — добавить аватарку
- `deleteStickerFromSet` — удалить одну аватарку
- `deleteStickerSet` — удалить весь pack
- `getUserProfilePhotos` — получить аватарку
- `getChatAdministrators` — список участников

## Зависимости

```toml
# pyproject.toml
[project]
dependencies = [
    "Pillow>=10.0.0",
]
```
