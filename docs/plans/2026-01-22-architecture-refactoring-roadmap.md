# Architecture Refactoring Roadmap

**Создан:** 2026-01-22
**Статус:** В работе

## Сделано

### Project restructure
Файлы разложены по провайдерам:
- `telegram/` — queue, adapters, keyboards, animations
- `tmux/` — sessions, launcher
- `claude/` — screen parsing, poller, history
- `git/` — worktree, utils
- `core/` — session_manager, coordinator

### Permission poller refactoring
God-function `permission_poller()` (598 LOC) разбита на handler классы:
- CompactHandler, ThinkingHandler, SuggestionsHandler, StuckHandler, PermissionHandler
- См. `docs/designs/done/2026-01-18-permission-poller-refactoring.md`

## В работе

_Пусто_

## Бэклог

### 1. handlers/start.py + services/start_flow.py (~1700 LOC)
**Проблема:** God-file, смешаны роутинг и бизнес-логика, FSM states + callbacks + messages в одном файле.

**Подход:**
- Разбить handler по типу событий (commands, callbacks, messages, fsm)
- Разбить service по этапам flow (detection, discovery, binding)
- Каждый файл < 300 LOC

### 2. claude/screen.py (437 LOC)
**Проблема:** 20+ regex паттернов, хрупкий парсинг tmux, ломается при изменении UI Claude, нет тестов.

**Подход:**
- Добавить unit-тесты на все паттерны
- Выделить парсеры в отдельные функции
- Документировать формат экрана Claude

### 3. FSM state management (две системы)
**Проблема:** aiogram FSMContext с ключом `(chat_id, user_id)` и кастомный `_flow_state` с ключом `(chat_id, thread_id)`. Дублирование, непонятно новичку, разный lifetime.

**Подход:**
- Написать `ThreadAwareStorage` с ключом `(chat_id, thread_id, user_id)`
- Мигрировать все flows на единую систему
- Удалить `_flow_state`

### 4. telegram/queue.py (510 LOC)
**Проблема:** Rate limiting, chunking, markdown escape, retry logic — много ответственностей в одном классе.

**Подход:**
- Выделить ChunkingMixin или отдельный Chunker
- Выделить MarkdownEscaper
- Оставить в queue только очередь и rate limiting

### 5. core/session_manager.py (502 LOC)
**Проблема:** ProjectState, ThreadInfo, ProjectManager в одном файле. Persistence + business logic смешаны.

**Подход:**
- Вынести models в `core/models.py`
- Вынести persistence в `core/storage.py`
- Оставить в manager только бизнес-логику

### 6. handlers/new_chat.py + handlers/finish_chat.py (~830 LOC)
**Проблема:** Дублирование логики создания/удаления threads и worktrees.

**Подход:**
- Вынести общую логику в `services/chat_lifecycle.py`
- Handlers только роутинг

### 7. claude/history_watcher.py (382 LOC)
**Проблема:** Parsing jsonl + formatting + sending в одном месте.

**Подход:**
- Выделить JsonlParser
- Выделить MessageFormatter
- Оставить в watcher только координацию

### 8. handlers/dm.py (450 LOC)
**Проблема:** DM onboarding, /dashboard, /check_env — разные команды в одном файле.

**Подход:**
- Разбить по командам: `dm/onboarding.py`, `dm/dashboard.py`, `dm/check_env.py`

### 9. handlers/migration.py (294 LOC)
**Проблема:** Group → supergroup migration, много Telegram API edge cases.

**Подход:**
- Добавить тесты на edge cases
- Документировать поведение Telegram API

### 10. handlers/setup/* (~1000 LOC)
**Проблема:** FSM для setup flow (clone, connect, new project), много файлов но тесно связаны.

**Подход:**
- Ревью после унификации FSM storage (#3)
- Возможно объединить мелкие файлы

## Принципы

1. **Handlers — только роутинг.** Принял event → вызвал service → отправил ответ.
2. **Services — бизнес-логика.** Не знают о Telegram API.
3. **Каждый файл < 300 LOC.** Исключения требуют обоснования.
4. **Тесты перед рефакторингом.** Сначала покрыть тестами, потом менять.
