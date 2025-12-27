# Telegram Display Samples

Примеры того, что отправлялось в Telegram из текущей сессии. Для анализа и улучшения отображения тулов.

## Оригинальные логи

Полные логи сохранены в `./2025-12-24-logs-snapshot/`:

| Файл | Описание |
|------|----------|
| `poller-sent.log` | Что отправлено в Telegram (финальный текст) |
| `poller-debug.log` | State machine поллера (IDLE→DEBOUNCING→SHOWING) |
| `poller-screen-raw.txt` | Сырой вывод tmux capture-pane |
| `poller-debug-screen.txt` | Парсинг экрана (body, options) |

## Permission Prompts (poller-sent.log)

### Bash command (kill)

```
Bash command

   kill 136858 2>/dev/null; sleep 1; ps aux | grep codogram | grep -v
   grep
   Kill old bot process

 Do you want to proceed?
OPTIONS:
1. Yes
2. Yes, and don't ask again for kill commands in
3. Type here to tell Claude what to do differently
```

### Bash command (journalctl)

```
Bash command

   cat /proc/162774/fd/1 2>/dev/null || journalctl --user -u codogram
   --no-pager -n 30 2>/dev/null || echo "no logs available"
   Try to get stdout from process

 Do you want to proceed?
OPTIONS:
1. Yes
2. Yes, and don't ask again for journalctl commands in
3. Type here to tell Claude what to do differently
```

### Bash command (pytest)

```
Bash command

   cd /home/superbereza/dev/personal-agent/agent-tools/codogram &&
   source ../../venv/bin/activate && python -m pytest
   tests/test_project_resolver.py -v
   Run pytest to verify test fails

 Do you want to proceed?
OPTIONS:
1. Yes
2. Yes, and don't ask again for source commands in
3. Type here to tell Claude what to do differently
```

### Bash command (tail logs)

```
Bash command

   tail -50
   /home/superbereza/dev/personal-agent/tmp/codogram-logs/*.log
   2>/dev/null
   Check bot logs

 Do you want to proceed?
OPTIONS:
1. Yes
2. Yes, and don't ask again for tail commands in
3. Type here to tell Claude what to do differently
```

## Наблюдения

### Проблемы отображения

1. **Длинные команды разрываются** — переносы строк внутри команды делают её нечитаемой
2. **Описание команды в конце** — "Kill old bot process" после команды, не до
3. **Дублирование** — "Bash command" в начале избыточно
4. **Опции слишком длинные** — "Yes, and don't ask again for kill commands in" обрезано

### Идеи улучшения

1. **Компактный формат:**
   ```
   🔧 Bash: Kill old bot process

   kill 136858 2>/dev/null; ...

   [Yes] [Always] [Edit]
   ```

2. **Описание первым** — важнее команды

3. **Сокращённые опции:**
   - Yes → ✓
   - Yes, don't ask again → ✓✓
   - Type here → ✏️

4. **Code block для команды** — моноширинный шрифт

## Watcher Output

TODO: собрать примеры из watcher (tool_use сообщения)

## Скрытые тулы

Тулы которые НЕ должны отображаться (нет в CLI):
- TodoWrite (?)
- Нужно исследовать какие ещё
