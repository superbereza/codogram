# Status Messages Unification

**Date:** 2026-01-17
**Status:** Ready for implementation

## Overview

Унификация статусных сообщений в Codogram:
- **Все тексты** в `strings.py` для централизованного управления tone-of-voice
- Отправка друг за другом (send) вместо редактирования (edit)
- Все сообщения заканчиваются финальным статусом

## Почему централизация

- Управление tone-of-voice в одном месте
- Легко ревьюить все сообщения
- Готовность к i18n (English версия)
- Стандартный подход (Android strings.xml, iOS Localizable.strings)

## Решения

### 1. Все сообщения как константы в strings.py

**Структура strings.py:**

```python
# === Status prefixes ===
STATUS_OK = "`[v]`"
STATUS_ERR = "`[x]`"
STATUS_WARN = "`[!]`"
STATUS_PENDING = "`[~]`"
STATUS_QUESTION = "`[?]`"
STATUS_INFO = "`[i]`"

# === Status messages ===
# Branch operations
BRANCH_CREATING = f"{STATUS_PENDING} Creating branch `{{name}}`..."
BRANCH_CREATED = f"{STATUS_OK} Branch `{{name}}` created"
BRANCH_MERGED = f"{STATUS_OK} Branch `{{name}}` merged"
BRANCH_MERGE_FAILED = f"{STATUS_ERR} Failed to merge: {{error}}"
BRANCH_PUSHING = f"{STATUS_PENDING} Pushing `{{branch}}`..."

# Thread/Topic operations
THREAD_CREATING = f"{STATUS_PENDING} Creating thread `{{name}}`..."
THREAD_CREATED = f"{STATUS_OK} Thread `{{name}}` created"
TOPIC_ARCHIVING = f"{STATUS_PENDING} Archiving `{{name}}`..."
TOPIC_ARCHIVED = f"{STATUS_OK} Topic `{{name}}` archived"
TOPIC_ARCHIVE_CONFIRM = f"{STATUS_QUESTION} Archive topic `{{name}}`?"

# Session operations
SESSION_CREATING = f"{STATUS_PENDING} Creating new session..."
SESSION_READY = f"{STATUS_OK} Claude ready"
SESSION_CLOSED = f"{STATUS_WARN} Claude session closed: {{name}}"

# Errors
ERR_PROJECT_NOT_FOUND = f"{STATUS_ERR} Project not found"
ERR_THREAD_NOT_FOUND = f"{STATUS_ERR} Thread not found"
ERR_WORKTREE_NOT_FOUND = f"{STATUS_WARN} Worktree not found: `{{path}}`"

# Prompts (без статуса)
PROMPT_PROJECT_NAME = "Отправь имя проекта:"
PROMPT_CUSTOM_PATH = "Отправь путь к директории:"
PROMPT_CLONE_URL = "Отправь ссылку на репозиторий:"

# ... все ~80+ сообщений
```

**Использование в хендлерах:**

```python
from .. import strings

# С параметрами
await telegram_queue.send(chat_id, strings.BRANCH_MERGED.format(name=branch_name), thread_id=thread_id)

# Без параметров
await telegram_queue.send(chat_id, strings.SESSION_READY, thread_id=thread_id)

# Промпты (без статуса, parse_mode=None)
await telegram_queue.edit(callback.message, strings.PROMPT_PROJECT_NAME, parse_mode=None)
```

**Форматтер-функции НЕ нужны** — константы уже содержат STATUS_* внутри.

### 2. Паттерн send vs edit

| Ситуация | Метод |
|----------|-------|
| Ответ на callback (убрать кнопки) | `edit` |
| Последующие статусы | `send` |
| Ответ на сообщение пользователя | `reply` |
| Launch animation (рожица) | `edit` (не трогаем) |

**Пример длинной операции (merge):**

```python
async def on_merge_confirm(callback, telegram_queue):
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    # 1. Убираем кнопки (edit)
    await telegram_queue.edit(callback.message, strings.BRANCH_MERGING.format(name=branch_name))
    await callback.answer()

    # 2. Последующие шаги (send)
    result = merge_branch(...)
    if not result.success:
        await telegram_queue.send(chat_id, strings.BRANCH_MERGE_FAILED.format(error=result.error), thread_id=thread_id)
        return

    await telegram_queue.send(chat_id, strings.BRANCH_PUSHING.format(branch=target_branch), thread_id=thread_id)

    # 3. Финальный статус (send)
    await telegram_queue.send(chat_id, strings.BRANCH_MERGED.format(name=branch_name), thread_id=thread_id)
```

**Пример создания (branch/thread):**

```python
async def on_branch_create_confirm(callback, telegram_queue):
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    # 1. Убираем кнопки (edit)
    await telegram_queue.edit(callback.message, strings.BRANCH_CREATING.format(name=branch_name))
    await callback.answer()

    # 2. Создаём бранч
    result = create_branch(...)

    # 3. Финальный статус (send)
    await telegram_queue.send(chat_id, strings.BRANCH_CREATED.format(name=branch_name), thread_id=thread_id)
```

**Правило:** Любая операция с кнопками заканчивается финальным статусом через `send`.

### 3. MarkdownV2 и parse_mode

**Правила:**

| Тип сообщения | parse_mode | Пример |
|---------------|------------|--------|
| Статусное (с `[v]`, `[x]`, etc.) | MarkdownV2 (дефолт) | `strings.SESSION_READY` |
| Промпт с backticks | MarkdownV2 (дефолт) | `"Send name (e.g. \`my-project\`):"` |
| Простой промпт | `None` | `strings.PROMPT_PROJECT_NAME` |

**Правило:** Если в сообщении есть backticks или статусный префикс → MarkdownV2.
Если простой текст без форматирования → можно `parse_mode=None`.

## Скоуп рефакторинга

### strings.py

Добавить:
- `STATUS_QUESTION`, `STATUS_INFO` (отсутствуют)
- Все сообщения из хендлеров (~80+ констант)
- Группировка по категориям (Branch, Topic, Session, Errors, Prompts, etc.)

### Файлы для рефакторинга

| Файл | Что делаем |
|------|-----------|
| `handlers/start.py` | ~25 сообщений → константы |
| `handlers/finish.py` | ~15 сообщений → константы, edit→send для цепочек |
| `handlers/branches.py` | ~10 сообщений → константы |
| `handlers/sessions.py` | ~5 сообщений → константы |
| `handlers/threads.py` | ~5 сообщений → константы |
| `handlers/worktree_recovery.py` | ~12 мест с `.edit_text()` → `telegram_queue.edit()` |
| `handlers/create_flow.py` | ~5 сообщений → константы |
| `handlers/common.py` | ~3 сообщения → константы |
| `services/launch.py` | ~5 сообщений → константы |
| `history_watcher.py` | ~5 сообщений → константы |
| `permission_poller.py` | ~3 сообщения → константы |

**Всего:** ~90+ сообщений для переноса в strings.py

**Не трогаем:** `launch_animation.py` (анимация рожицы)

## Использование strings в layered architecture

| Слой | Использует strings? |
|------|---------------------|
| `handlers/*` | ✅ ДА — основной потребитель |
| `services/*` | ✅ ДА — для сообщений об ошибках |
| `domain/*` | ❌ НЕТ — чистые модели без сообщений |
| Core modules (`history_watcher`, `permission_poller`) | ✅ ДА — через strings |

## Чеклист

- [ ] Добавить `STATUS_QUESTION`, `STATUS_INFO` в strings.py
- [ ] Собрать все сообщения из кода, сгруппировать
- [ ] Добавить константы в strings.py
- [ ] Рефакторинг handlers/* — заменить хардкод на константы
- [ ] Рефакторинг services/, history_watcher.py, permission_poller.py
- [ ] Исправить worktree_recovery.py: `.edit_text()` → `telegram_queue.edit()`
- [ ] Применить паттерн send vs edit для цепочек статусов
- [ ] Тестирование
- [ ] Обновить E2E тесты если изменился flow

## Naming Convention

Константы именуются по паттерну:
```
{CATEGORY}_{ACTION}_{DETAIL}

# Примеры:
BRANCH_MERGED              # OK статус
BRANCH_MERGE_FAILED        # ERR статус
BRANCH_MERGING             # PENDING статус
BRANCH_MERGE_CONFIRM       # QUESTION статус

TOPIC_ARCHIVED
TOPIC_ARCHIVING
TOPIC_ARCHIVE_CONFIRM

ERR_PROJECT_NOT_FOUND
ERR_THREAD_NOT_FOUND

PROMPT_PROJECT_NAME
PROMPT_CUSTOM_PATH
```

## Многострочные сообщения

Одна константа с triple quotes:

```python
TOPIC_ARCHIVE_CONFIRM = f"""{STATUS_QUESTION} Archive topic `{{name}}`?

This will close the topic and stop Claude session."""
```

**Не разбиваем** на части — сообщение это единица коммуникации.
Исключение: если часть реально переиспользуется в 2+ местах.

## Тексты кнопок

Типовые кнопки тоже выносим в strings.py:

```python
# === Button texts (без backticks — не markdown) ===
BTN_YES = "Yes"
BTN_NO = "No"
BTN_CANCEL = "Cancel"
BTN_BACK = "[<<] Back"
BTN_CONFIRM = "Confirm"

# Специфичные
BTN_YES_MERGE = "Yes, merge"
BTN_YES_LAUNCH = "Yes, launch"
BTN_CREATE_DIR = "Create directory"
BTN_CUSTOM_PATH = "Custom path"
```

**Правило:** Если кнопка используется в 2+ местах → константа.
Уникальные кнопки можно оставить inline.
