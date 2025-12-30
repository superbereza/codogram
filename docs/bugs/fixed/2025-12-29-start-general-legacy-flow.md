# Bug: /start в General использует legacy flow

**Date:** 2025-12-29
**Severity:** Medium
**Status:** Fixed (2025-12-30)

## Summary

При `/start` в General (thread_id=None) мультигруппы, код использует legacy flow с `find_all_tmux_by_cwd`, который находит ВСЕ tmux сессии в директории проекта, включая tmux других тредов.

## Reproduction steps

1. Создать мультигруппу с проектом "codogram"
2. Создать несколько тредов через /session_new (ancient, sublime)
3. Запустить Claude во всех тредах
4. Выполнить /start в General
5. **Bug:** Показывает выбор из ВСЕХ tmux (claude-codogram, claude-codogram-ancient, claude-codogram-sublime)

## Expected behavior

/start в General должен:
1. Искать только `claude-{project}` (main thread tmux)
2. Использовать threads[None] с name="main"
3. Не показывать tmux других тредов

## Root cause

В `cmd_start` (bot.py:365-366), когда thread_id=None и проект существует:

```python
if project:
    await _start_project_flow(message, project)
```

`_start_project_flow` → `_connect_or_launch` → `find_all_tmux_by_cwd` — ищет ВСЕ tmux по cwd.

## Current flows

### Flow A: /start в General, cwd существует (BROKEN)
```
cmd_start
  → _start_project_flow
    → _connect_or_launch
      → find_all_tmux_by_cwd (ищет ВСЕ tmux!)
      → если несколько → показывает выбор всех
```

### Flow B: /start в General, cwd НЕ существует (OK)
```
cmd_start
  → _start_project_flow
    → показывает "Директория не найдена"
    → callback → launch_claude_new
      → создаёт threads[None] name="main" ✓
```

### Flow C: /start в топике (OK)
```
cmd_start
  → _start_thread_flow
    → ищет tmux по конвенции для треда ✓
```

## Proposed fix

Заменить Flow A на thread-based flow:

```python
# Было (строки 365-366):
if project:
    await _start_project_flow(message, project)

# Должно быть:
if project:
    if project.cwd and Path(project.cwd).is_dir():
        # cwd exists - use thread flow
        thread = project.get_or_create_thread(None, "main")
        await _start_thread_flow(message, project, thread)
        project_manager._save()
    else:
        # cwd doesn't exist - need setup
        await _start_project_flow(message, project)
```

## Open questions

1. **Обычный чат vs мультигруппа:** Нужно ли разное поведение? Сейчас обычный чат тоже использует discovery.

2. **Нестандартные имена tmux:** Если пользователь создал tmux вручную с нестандартным именем, как подключиться?
   - Вариант A: Игнорировать, требовать конвенцию
   - Вариант B: Fallback на discovery если конвенция не найдена

3. **Как определить мультигруппа или обычный чат:** Использовать `chat.is_forum`?

## Fix

Применён proposed fix в `bot.py:365-374`:

```python
if project:
    if project.cwd and Path(project.cwd).is_dir():
        # cwd exists - use thread flow (respects naming convention)
        thread = project.get_or_create_thread(None, "main")
        await _start_thread_flow(message, project, thread)
        project_manager._save()
    else:
        # cwd doesn't exist - need setup
        await _start_project_flow(message, project)
    return
```

Теперь `/start` в General использует `_start_thread_flow`, который ищет только `claude-{project}` по конвенции.

## Related

- docs/specs/start-scenarios-coverage.md
- docs/designs/2025-12-28-unified-thread-architecture.md
