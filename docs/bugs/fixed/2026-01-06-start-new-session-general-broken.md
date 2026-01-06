# "Start new session" не работает в General чате

**Найден в тесте:** R5
**Severity:** critical
**Status:** active

## Воспроизведение

1. В General чате с существующей сессией
2. Удалить jsonl файл сессии
3. Отправить /start
4. Нажать "Start new session"

## Ожидаемый результат

Claude запускается, новая сессия создаётся

## Фактический результат

Сообщение "[~] Starting new session..." появляется, но Claude НЕ запускается

## Причина

`src/codogram/handlers/start.py:624`:
```python
thread = project.threads.get(thread_id) if thread_id else None
```

Для General чата `thread_id=None`. Условие `if thread_id` возвращает `False`,
поэтому `thread` становится `None`.

Затем на строке 640:
```python
if thread:
    thread.launch_task = asyncio.create_task(...)
```

`if thread` тоже `False`, поэтому launch task никогда не создаётся!

## Фикс

Строка 624 должна быть:
```python
thread = project.threads.get(thread_id)  # Убрать "if thread_id else None"
```

Это работает потому что `project.threads.get(None)` корректно возвращает General thread
(ключ в словаре - `None`, не строка `"null"`).

## Логи

```
2026-01-06 13:59:01 [INFO] aiogram.event: Update id=486068874 is handled. Duration 227 ms
```
Callback обработан, но нет логов о запуске Claude.
