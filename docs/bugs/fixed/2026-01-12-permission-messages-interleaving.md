# Permission messages interleaved with other messages

**Severity:** minor (UX)
**Status:** active
**Found during:** MCP trust prompt E2E testing

## Симптомы

Сообщения permission poller перемешиваются с сообщениями launch_animation:

```
[поллер] ──────────── body
[поллер] options 1,2,3
[launch] [v] Claude ready    ← вклинилось
[поллер] 👆 keyboard
```

Должно быть:
```
[поллер] ──────────── body
[поллер] options 1,2,3
[поллер] 👆 keyboard
[launch] [v] Claude ready
```

## Причина

Permission poller делает **2 отдельных `enqueue()`**:

```python
# permission_poller.py, строки 202-217
content_msg_ids = await telegram_queue.enqueue(batch)      # 1. body + options
# <-- сюда может вклиниться launch_animation
kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch)   # 2. keyboard
```

Между двумя `await` другие корутины могут добавить свои сообщения в очередь.

## Решение

Нужна атомарность батча. Варианты:

### Вариант 1: Объединить в один батч (рекомендуется)
Добавить поддержку `reply_markup` в `OutgoingBatch`, чтобы последнее сообщение батча получало клавиатуру:

```python
batch = OutgoingBatch(
    chat_id=project.chat_id,
    thread_id=thread_id,
    messages=body_messages,
    reply_markup=kb,  # NEW: клавиатура на последнее сообщение
)
content_msg_ids = await telegram_queue.enqueue(batch)
kb_msg_id = content_msg_ids[-1]  # последнее сообщение = с клавиатурой
```

### Вариант 2: Batch lock
Добавить механизм "batch transaction" в очередь — пока batch не закрыт, другие ждут.

### Вариант 3: Приоритеты
Permission prompts имеют высокий приоритет и не прерываются.

## Затронутые файлы

- `src/codogram/telegram_queue.py` — добавить reply_markup в OutgoingBatch
- `src/codogram/permission_poller.py` — использовать один enqueue вместо двух

## Связанные баги

- [2026-01-12-permission-cleanup-incomplete.md](2026-01-12-permission-cleanup-incomplete.md) — возможно следствие этого же бага
