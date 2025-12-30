# Bug: /start в новом топике использует magic name вместо запроса имени

**Date:** 2025-12-29
**Severity:** Low
**Status:** Open

## Summary

При `/start` в незарегистрированном топике или pending треде, код автоматически генерирует magic name (ancient, sublime, immortal...) вместо того, чтобы спросить пользователя как назвать тред.

## Reproduction steps

1. Создать мультигруппу с проектом
2. Вручную создать топик в Telegram (не через /session_new)
3. Выполнить /start в этом топике
4. **Bug:** Тред получает случайное magic name вместо осмысленного имени

## Expected behavior

При /start в незарегистрированном топике бот должен:
1. Спросить пользователя: "Как назвать этот тред?"
2. Предложить варианты: ввести имя вручную / использовать magic name
3. Использовать введённое имя для tmux конвенции

## Current behavior

Код автоматически генерирует magic name:

**Для pending треда (bot.py:317-321):**
```python
if thread.name == "pending":
    from .magic_names import get_random_magic_name
    existing_names = {t.name for t in project.threads.values() if t.name != "pending"}
    thread.name = get_random_magic_name(existing_names)
```

**Для незарегистрированного топика (bot.py:331-334):**
```python
from .magic_names import get_random_magic_name
existing_names = {t.name for t in project.threads.values() if t.name != "pending"}
thread_name = get_random_magic_name(existing_names)
```

## Why magic names exist

Magic names были добавлены как временное решение, потому что:
1. Telegram Bot API не даёт получить название топика по thread_id
2. Нужно было быстрое решение для именования тредов

## Proposed fix

Добавить диалог запроса имени:

```python
# Вместо автоматического magic name:
if thread.name == "pending" or thread not in project.threads:
    # Сохранить состояние
    _start_state[chat_id] = {
        "state": "awaiting_thread_name",
        "thread_id": thread_id,
    }

    # Показать клавиатуру
    await message.answer(
        "Как назвать этот тред?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎲 Случайное имя", callback_data="thread_name:magic")],
        ])
    )
    await message.answer("Или отправь имя текстом (например: `bugfix`, `feature-auth`)")
    return
```

## Trade-offs

**Плюсы запроса имени:**
- Пользователь контролирует имена тредов
- Более осмысленные имена для tmux сессий
- Легче ориентироваться в `tmux ls`

**Минусы:**
- Дополнительный шаг для пользователя
- /session_new уже позволяет задать имя явно

## Alternative: Use topic title

Telegram Bot API не даёт получить topic title напрямую. Варианты:
1. Добавить Telethon/MTProto для получения topic title (overkill)
2. Слушать service messages ForumTopicCreated (работает только для новых топиков)
3. Спрашивать пользователя (предложенное решение)

## Open questions

1. **UX:** Спрашивать всегда или только для вручную созданных топиков?

2. **Default:** Если пользователь не ответил, использовать magic name или ждать?

3. **Валидация:** Какие символы разрешены в имени треда?

## Related

- docs/bugs/2025-12-29-start-general-legacy-flow.md
- docs/specs/start-scenarios-coverage.md
