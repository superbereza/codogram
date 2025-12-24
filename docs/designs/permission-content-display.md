# Permission Content Display

## Проблема

При permission prompt в jsonl приходит только:
```json
{"name": "Write", "input": {"file_path": "test.txt", "content": "hello world"}}
```

А в терминале отображается полный контент (diff, описание, вопрос). Сейчас показываем только `● Write path` + кнопки, теряя контекст.

## Решение

Парсить полный текст permission из tmux capture-pane, отправлять в Telegram, удалять после ответа.

## Архитектура

**Флоу:**
```
jsonl: tool_use → poll tmux → parse permission content →
TG: [content message(s)] + keyboard →
user clicks → delete all messages + send key
```

## Парсинг контента

**Структура permission в терминале:**
```
● Write(test.txt)                          ← tool header (в jsonl)
──────────────────────────────────────     ← separator solid
 Create file test.txt                      ← description
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌     ← separator dashed
  1 hello world                            ← content (diff/preview)
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌     ← separator dashed
 Do you want to create test.txt?           ← question
 ❯ 1. Yes                                  ← options
   2. Yes, allow all...
```

**Расширение PermissionPrompt:**
```python
@dataclass
class PermissionPrompt:
    options: list[str]           # ["1. Yes", "2. Yes, allow..."]
    description: str = ""        # "Create file test.txt"
    content: str = ""            # diff/preview между ╌╌╌ маркерами
    question: str = ""           # "Do you want to create test.txt?"
```

## Отображение в Telegram

**Константы:**
```python
SEPARATOR_SOLID = "─" * 20   # настраиваемая длина
SEPARATOR_DASHED = "╌" * 20
```

**Формат:**
```
────────────────────
Create file test.txt
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 hello world
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
Do you want to create test.txt?

[Yes] [Yes, allow all] [❌ Cancel]
```

**Стратегия:**
- Один message с контентом + keyboard (если < 4096 символов)
- Если длинный — чанкуем, keyboard на последнем
- Трекаем все message_id

## Хранение message_id

```python
# main.py
permission_messages: dict[int, list[int]] = {}
# {keyboard_msg_id: [content_msg_id1, content_msg_id2, ...]}
```

Очистка через `pop()` в callback. Для MVP без лимита — YAGNI.

## Удаление сообщений

```python
@router.callback_query(F.data.startswith("perm:"))
async def on_permission_callback(callback: CallbackQuery):
    kb_msg_id = callback.message.message_id

    # Удаляем контент-сообщения
    content_ids = permission_messages.pop(kb_msg_id, [])
    for msg_id in content_ids:
        try:
            await callback.bot.delete_message(settings.chat_id, msg_id)
        except Exception:
            pass

    # Удаляем сообщение с keyboard
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Отправляем key в tmux
    action = callback.data.split(":")[1]
    s = get_session()
    s.send_key("Escape" if action == "esc" else action)

    await callback.answer()
```

## Файлы

| Файл | Изменения |
|------|-----------|
| `screen.py` | Расширить `PermissionPrompt` + парсинг контента |
| `main.py` | `permission_messages` dict, форматирование, отправка |
| `bot.py` | Удаление всех сообщений в callback |
