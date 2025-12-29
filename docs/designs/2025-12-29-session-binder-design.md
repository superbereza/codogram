# Session Binder Design

## Проблема

**Баг:** Thread session mixup — когда новая сессия появляется в одном треде (через /start, /new, /compact), другие треды ошибочно теряют свою привязку.

**Root cause:** `check_session_for_thread()` использует `find_session_for_project(cwd)` который возвращает последнюю сессию **проекта**, а не сессию конкретного треда.

```python
# Сломанный код (history_watcher.py:250)
async def check_session_for_thread(...):
    new_session_id = find_session_for_project(project.cwd)  # ← БАГ
    if new_session_id != old_session:
        # Отменяет watcher — но new_session может быть от другого треда!
```

## Решение

Новый сервис `SessionBinderService` с разной логикой для разных типов чатов:
- **Single-thread (обычный чат):** старая логика `find_session_for_project`
- **Multi-thread (мультичат):** content matching через capture-pane

## Архитектура

Вписывается в layer-based архитектуру из bot-refactoring дизайна:

```
handlers/messages.py  →  services/session_binder.py  →  adapters/
                              ↑
HistoryWatcher._check_for_changes()
```

### Новые файлы

```
src/codogram/
├── services/
│   └── session_binder.py    # SessionBinderService
```

### Точки вызова

1. **on_message** (`handlers/messages.py`) — при каждом сообщении пользователя
2. **HistoryWatcher** — каждые 15 сек в background

## SessionBinderService

```python
class SessionBinderService:
    """Binds Claude sessions to threads via content matching."""

    def __init__(self, tmux_adapter, history_adapter):
        self.tmux = tmux_adapter
        self.history = history_adapter

    async def check_and_bind(self, project: ProjectState) -> None:
        """Entry point — выбирает стратегию по типу чата."""
        if self._is_multi_thread(project):
            await self._bind_multi_thread(project)
        else:
            await self._bind_single_thread(project)

    def _is_multi_thread(self, project: ProjectState) -> bool:
        """Проект мультичат если есть топики (thread_id != None)."""
        return any(t.thread_id is not None for t in project.threads.values())

    # === Single-thread (обычный чат) ===

    async def _bind_single_thread(self, project: ProjectState) -> None:
        """Старая логика: find_session_for_project."""
        thread = project.threads.get(None)
        if not thread:
            return

        new_session = self.history.find_session_for_project(project.cwd)

        if new_session and new_session != thread.session_id:
            logger.info(f"session_changed_single: {thread.session_id} -> {new_session}")
            await self._rebind_thread(project, thread, new_session)

    # === Multi-thread (мультичат) ===

    async def _bind_multi_thread(self, project: ProjectState) -> None:
        """Content matching для каждой unbound сессии."""
        unbound = self._find_unbound_sessions(project)

        for session_id in unbound:
            await self._try_bind_via_content(project, session_id)

    def _find_unbound_sessions(self, project: ProjectState) -> set[str]:
        """Найти сессии без привязки к тредам."""
        project_dir = self.history.get_project_dir(project.cwd)
        all_sessions = {f.stem for f in project_dir.glob("*.jsonl")}
        bound = {t.session_id for t in project.threads.values() if t.session_id}
        return all_sessions - bound

    async def _try_bind_via_content(self, project: ProjectState, session_id: str) -> None:
        """Match content с capture-pane тредов."""
        jsonl_path = self.history.compute_jsonl_path(project.cwd, session_id)
        content = self._extract_matchable_content(jsonl_path)

        if not content:
            logger.debug(f"no matchable content: session={session_id[:8]}")
            return  # Пустой jsonl, попробуем позже

        logger.debug(f"trying to bind session={session_id[:8]}, content={content[:50]}...")

        for thread in project.threads.values():
            if thread.session_id:
                continue  # Уже привязан

            tmux_name = thread.get_tmux_session(project.project_name)
            pane = self.tmux.capture_pane(tmux_name)

            if self._content_matches(content, pane):
                logger.info(f"session_bound_content: thread={thread.name}, session={session_id[:8]}")
                await self._rebind_thread(project, thread, session_id)
                break
        else:
            logger.debug(f"no match found for session={session_id[:8]}")

    # === Content matching ===

    def _extract_matchable_content(self, jsonl_path: Path) -> str | None:
        """Извлечь контент для matching из последней записи."""
        last_entry = self.history.read_last_assistant_entry(jsonl_path)
        if not last_entry:
            return None

        content = last_entry.get("message", {}).get("content", [])

        for item in content:
            if item.get("type") == "text":
                # Текстовый ответ — первые 200 символов
                return item.get("text", "")[:200]

            elif item.get("type") == "tool_use":
                # Tool call — имя + часть input
                name = item.get("name", "")
                inp = str(item.get("input", {}))[:100]
                return f"tool:{name}:{inp}"

        return None

    def _content_matches(self, content: str, pane: str) -> bool:
        """Проверить есть ли content в capture-pane."""
        if not content or not pane:
            return False

        if content.startswith("tool:"):
            # Tool call: ищем имя и часть input
            parts = content.split(":", 2)
            if len(parts) < 3:
                logger.warning(f"malformed tool content: {content}")
                return False
            _, tool_name, tool_input = parts
            return tool_name in pane and tool_input[:50] in pane
        else:
            # Текст: substring match
            return content[:150] in pane

    # === Rebind ===

    async def _rebind_thread(
        self,
        project: ProjectState,
        thread: ThreadInfo,
        new_session_id: str
    ) -> None:
        """Перепривязать тред к новой сессии."""
        # Отменить старый watcher
        if thread.watcher_task:
            thread.watcher_task.cancel()
            thread.watcher_task = None

        # Обновить привязку
        thread.session_id = new_session_id
        thread.jsonl_path = str(self.history.compute_jsonl_path(project.cwd, new_session_id))

        # Запустить новый watcher
        # (детали зависят от интеграции с существующим кодом)
```

## Вспомогательные методы

### TmuxAdapter (adapters/tmux.py)

```python
def capture_pane(self, session_name: str) -> str:
    """Capture entire scrollback from tmux pane.

    Uses -S - to get full history, not just visible area.
    This ensures we find content even if Claude scrolled past it.
    """
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.debug(f"capture_pane failed: {session_name}, rc={result.returncode}")
        return ""
    return result.stdout
```

### HistoryAdapter (adapters/history.py)

```python
from .history_reader import compute_jsonl_path  # Reuse existing function

def get_project_dir(self, cwd: str) -> Path:
    """Get project directory for jsonl files.

    Reuses normalization logic from compute_jsonl_path.
    """
    normalized = cwd.rstrip("/") or "/"
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    project_hash = normalized.replace("/", "-")
    return Path.home() / ".claude" / "projects" / project_hash

def read_last_assistant_entry(self, jsonl_path: Path) -> dict | None:
    """Read last assistant entry from jsonl."""
    if not jsonl_path.exists():
        logger.debug(f"jsonl not found: {jsonl_path}")
        return None

    last_entry = None
    with open(jsonl_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("message", {}).get("role") == "assistant":
                    last_entry = entry
            except json.JSONDecodeError:
                continue

    logger.debug(f"read_last_assistant_entry: {jsonl_path.name}, found={last_entry is not None}")
    return last_entry
```

## Интеграция

### handlers/messages.py

```python
async def on_message(message: Message, session_binder: SessionBinderService):
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        return

    # Check and bind sessions
    await session_binder.check_and_bind(project)

    # ... rest of message handling
```

### HistoryWatcher

```python
async def _check_for_changes(self):
    for project in self.project_manager.projects.values():
        # ... cleanup checks ...

        # Bind sessions
        await self.session_binder.check_and_bind(project)
```

## Что удаляем

1. **`check_session_for_thread()`** в `history_watcher.py` — заменяется на SessionBinderService
2. Вызов `check_session_for_thread` в `bot.py` on_message — заменяется на session_binder.check_and_bind

## Что остаётся

1. **`poll_for_session_thread()`** — binding по user message (fallback)
2. **`watch_thread_jsonl()`** — watcher для треда
3. **`find_session_for_project()`** — используется внутри SessionBinderService для single-thread

## Edge cases

### Несколько тредов без session_id

Проходим треды по порядку, первый match wins. Два tmux не могут иметь одинаковый content одновременно.

### Orphan сессии (локальная работа)

Сессии без match в tmux игнорируются. Content matching не найдёт совпадение, сессия останется unbound.

### Claude ещё не ответил

Если jsonl пустой или нет assistant entry — пропускаем, попробуем на следующем цикле (15 сек).

## Тестирование

```python
# Unit tests
def test_is_multi_thread_single():
    project = ProjectState(threads={None: ThreadInfo(thread_id=None, name="main")})
    assert not session_binder._is_multi_thread(project)

def test_is_multi_thread_multi():
    project = ProjectState(threads={
        None: ThreadInfo(thread_id=None, name="main"),
        123: ThreadInfo(thread_id=123, name="topic"),
    })
    assert session_binder._is_multi_thread(project)

def test_content_matches_text():
    assert session_binder._content_matches("Hello world", "Some text Hello world more text")
    assert not session_binder._content_matches("Hello world", "Goodbye")

def test_content_matches_tool():
    assert session_binder._content_matches("tool:Bash:ls -la", "● Bash(ls -la)")
```

## Rollout

1. Создать `services/session_binder.py`
2. Добавить `capture_pane` в tmux.py
3. Добавить helper методы в history_reader.py
4. Интегрировать в on_message
5. Интегрировать в HistoryWatcher
6. Удалить `check_session_for_thread`
7. Тестирование на мультичате

## Изменения после ревью

**v2 (2025-12-29):**

1. **ValueError fix** — добавлена проверка `len(parts) < 3` в `_content_matches()` для tool calls

2. **Полный scrollback** — `capture_pane()` использует `-S -` вместо `-S -100`, захватывает всю историю tmux. Это надёжнее чем матчить несколько записей.

3. **Переиспользование кода** — `compute_jsonl_path()` импортируется из существующего `history_reader.py`

4. **Логирование** — добавлены debug логи для отладки content matching:
   - `no matchable content` — jsonl пустой
   - `trying to bind` — начало поиска
   - `session_bound_content` — успешный match
   - `no match found` — не нашли подходящий tmux
   - `capture_pane failed` — ошибка захвата tmux
   - `malformed tool content` — неверный формат tool call
