# Permission messages not fully deleted on button click

**Severity:** minor
**Status:** active
**Found during:** MCP trust prompt E2E testing

## Симптомы

При клике на кнопку permission prompt удаляется только сообщение с клавиатурой (👆), но body и options остаются висеть.

## Контекст

Обнаружено при тестировании MCP trust prompt. Между сообщениями поллера вклинилось сообщение от launch_animation:

```
[поллер] ──────────── body
[поллер] options 1,2,3
[launch] [v] Claude ready    ← вклинилось между
[поллер] 👆 keyboard
```

После клика удалилась только клавиатура.

## Возможные причины

1. **Race condition** — поллер делает `permission_messages.pop()` в SHOWING->IDLE раньше чем хэндлер
2. **Interleaving** — из-за двух отдельных `enqueue()` что-то ломается в tracking
3. **content_msg_ids пустой** — `telegram_queue.enqueue()` вернул пустой список

## Архитектура проблемы

Поллер делает 2 отдельных вызова:
```python
content_msg_ids = await telegram_queue.enqueue(batch)      # body + options
kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch)   # keyboard
permission_messages[kb_msg_id] = content_msg_ids
```

Между ними может вклиниться launch_animation (тоже через очередь).

## Добавленные логи

### permission_poller.py (строка ~221)
```python
logger.debug(f"{log_prefix}: saved permission_messages[{kb_msg_id}] = {content_msg_ids}")
```

### handlers/permissions.py (cleanup)
```python
logger.debug(f"cleanup: kb_msg_id={kb_msg_id}, permission_messages keys={list(permission_messages.keys())}")
logger.debug(f"cleanup: content_ids={content_ids}")
logger.debug(f"cleanup: deleted content msg {msg_id}")
logger.warning(f"cleanup: failed to delete content msg {msg_id}: {e}")
```

## Как воспроизвести

1. Запустить бота в worktree с MCP сервером в `.mcp.json`
2. Дождаться MCP trust prompt
3. Кликнуть на кнопку выбора
4. Проверить удалились ли все сообщения

## Что смотреть в логах

При воспроизведении проверить:

1. **saved permission_messages[X] = [Y, Z]** — что поллер сохранил (должны быть ID body и options)
2. **cleanup: content_ids=[...]** — что хэндлер нашёл (должно совпадать с п.1)
3. Если `content_ids=[]` — значит race condition или mapping потерян

## Связанные задачи

- Атомарность батчей в telegram_queue (interleaving fix)
- После фикса interleaving этот баг может уйти сам

## Воспроизведение

- [ ] Пока не воспроизведён повторно
