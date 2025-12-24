# Background Permission Poller Design

## Проблема

Текущая архитектура сломана:

```
watcher_task:
  for entry in jsonl:
    if TOOL_USE:
      while True:  ← БЛОКИРУЕТ весь watcher
        poll tmux
```

**Проблемы:**
1. `watcher.py` баг — `content` может содержать строки, `item.get()` падает
2. Blocking loop — polling внутри watcher блокирует обработку jsonl
3. Self-monitoring — видим свои собственные tool_use в tmux, loop не выходит

## Архитектура

Два независимых asyncio task:

```
┌─────────────────────┐     ┌──────────────────────┐
│   watcher_task      │     │ permission_poller    │
│   (jsonl)           │     │ (tmux)               │
├─────────────────────┤     ├──────────────────────┤
│ TEXT → send         │     │ poll every 0.5s      │
│ TOOL_USE → send     │     │ detect Permission    │
│ (no blocking!)      │     │ debounce 0.5s        │
└─────────────────────┘     │ send content+kb      │
                            │ track msg_ids        │
                            └──────────┬───────────┘
                                       │
                            ┌──────────▼───────────┐
                            │  callback_handler    │
                            │  (button click)      │
                            ├──────────────────────┤
                            │ delete messages      │
                            │ send key to tmux     │
                            └──────────────────────┘
```

**Решения:**
- TOOL_USE: показываем кратко без polling
- State sharing: глобальный dict в `state.py`
- Race condition: try/except на delete

## State Machine

```
States:
  IDLE          # нет активного permission
  DEBOUNCING    # permission detected, ждём 0.5s стабильности
  SHOWING       # отправлено в Telegram, ждём ответ

Transitions:
  IDLE + PermissionPrompt → DEBOUNCING (start timer)

  DEBOUNCING + 0.5s passed + same options → SHOWING (send to TG)
  DEBOUNCING + options changed → DEBOUNCING (restart timer)
  DEBOUNCING + no permission → IDLE

  SHOWING + no permission → IDLE (cleanup messages)
  SHOWING + options changed → update keyboard
  SHOWING + callback → IDLE (callback handles cleanup)
```

**Debounce нужен потому что:**
- Permission может мелькнуть на экране при быстрых tool_use
- Ждём 0.5s чтобы убедиться что это реальный prompt

**Race condition handling:**
```python
try:
    await bot.delete_message(chat_id, msg_id)
except Exception:
    pass  # Already deleted by other party
```

## Файлы

| Файл | Действие |
|------|----------|
| `watcher.py` | Фикс: добавить `isinstance(item, dict)` check |
| `permission_poller.py` | Создать: state machine, polling, отправка |
| `main.py` | Убрать blocking loop, запустить poller task |
| `state.py` | Без изменений |
| `bot.py` | Без изменений |

## Edge Cases

| Случай | Поведение |
|--------|-----------|
| Permission меняется во время debounce | Рестарт debounce |
| Бот перезапустился с активным permission | Старые сообщения останутся (MVP ok) |
| User ответил в терминале | Poller детектит Idle, удаляет сообщения |
| Несколько permissions подряд | Debounce отфильтрует промежуточные |
