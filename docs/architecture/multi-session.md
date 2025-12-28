# Multi-Session Architecture

Архитектура поддержки нескольких Claude сессий в одном Telegram чате.

## Типы чатов

| Тип | chat.id | message_thread_id | Сессий Claude |
|-----|---------|-------------------|---------------|
| Private | > 0 | всегда None | 1 |
| Simple Group | < 0 | всегда None | 1 |
| Forum Group | < 0 (-100...) | None или int | 1+ (General + топики) |

## Структуры данных

### ProjectState

Основной объект проекта, связывает Telegram чат с директорией.

```python
@dataclass
class ProjectState:
    project_name: str
    chat_id: int | None          # Telegram group/chat ID
    cwd: str | None              # Project directory

    # Multi-thread support
    threads: dict[int | None, ThreadInfo]
    # Key: thread_id (None = General, int = Topic ID)
```

### ThreadInfo

Состояние отдельного топика/треда.

```python
@dataclass
class ThreadInfo:
    thread_id: int | None        # None = General, int = Topic ID
    name: str                    # "main", "mystic", "arcane", etc.

    # Session state
    session_id: str | None       # Claude session ID
    jsonl_path: str | None       # Path to session.jsonl

    # Tasks
    watcher_task: asyncio.Task   # Watches jsonl for responses
    poller_task: asyncio.Task    # Polls for permission prompts
    binding_task: asyncio.Task   # Waits for session binding

    # Binding state
    last_sent_message: str | None
    awaiting_new_session: bool

    def get_tmux_session(self, project_name: str) -> str:
        if self.name == "main":
            return f"claude-{project_name}"
        return f"claude-{project_name}-{self.name}"
```

### Карта связей

```
ProjectState (chat_id=123)
├── threads[None]      ← General (thread_id=None)
│   ├── session_id_A
│   ├── jsonl_path_A   → ~/.claude/projects/{hash}/session_A.jsonl
│   ├── watcher_task   → watch_thread_jsonl() → message_thread_id=None
│   └── poller_task    → permission_poller() → message_thread_id=None
│
├── threads[456]       ← Topic "Debugging"
│   ├── session_id_B
│   ├── jsonl_path_B   → ~/.claude/projects/{hash}/session_B.jsonl
│   ├── watcher_task   → watch_thread_jsonl() → message_thread_id=456
│   └── poller_task    → permission_poller() → message_thread_id=456
│
└── threads[789]       ← Topic "Features"
    ├── session_id_C
    ├── jsonl_path_C   → ~/.claude/projects/{hash}/session_C.jsonl
    ├── watcher_task   → watch_thread_jsonl() → message_thread_id=789
    └── poller_task    → permission_poller() → message_thread_id=789
```

## Claude файловая структура

```
~/.claude/
├── history.jsonl                           # Главный лог сеансов
│   └─ {"project": "/path/to/cwd", "sessionId": "abc123", ...}
│
└── projects/{cwd_hash}/                    # Данные по проекту
    ├── {session_id_1}.jsonl                # Messages для сеанса 1
    ├── {session_id_2}.jsonl                # Messages для сеанса 2
    └── {session_id_3}.jsonl                # Messages для сеанса 3
```

**Важно:** `history.jsonl` хранит только ПОСЛЕДНИЙ session_id для каждого cwd.
Для multi-thread нужно сканировать ВСЕ jsonl файлы по содержимому сообщений.

## Message Flow

### Входящее сообщение

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. USER SENDS MESSAGE                                           │
└─────────────────────────────────────────────────────────────────┘

Telegram event:
  chat_id = 123
  thread_id = 456 (or None for General)
  text = "fix bug"

┌─────────────────────────────────────────────────────────────────┐
│ 2. ROUTING in on_message()                                      │
└─────────────────────────────────────────────────────────────────┘

on_message():
  project = get_by_chat(123)
  thread = project.threads.get(thread_id)

  if not thread:
      thread = create_thread(thread_id)

  tmux_name = thread.get_tmux_session(project.project_name)
  tmux = TmuxSession(tmux_name, project.cwd)
  tmux.send("fix bug")

┌─────────────────────────────────────────────────────────────────┐
│ 3. CLAUDE PROCESSES IN TMUX                                     │
└─────────────────────────────────────────────────────────────────┘

tmux: claude-my-project-mystic
  ├─ Receives: "fix bug"
  └─ Writes to: ~/.claude/projects/{hash}/session_B.jsonl

┌─────────────────────────────────────────────────────────────────┐
│ 4. WATCHER DETECTS RESPONSE                                     │
└─────────────────────────────────────────────────────────────────┘

watch_thread_jsonl(thread):
  ├─ Watches: thread.jsonl_path
  ├─ Detects new entry
  └─ Sends:
      bot.send_message(
          chat_id=123,
          text=response,
          message_thread_id=456  ← CORRECT THREAD!
      )
```

### Изоляция сообщений

Каждый thread имеет:
- Свой tmux session (`claude-project` vs `claude-project-mystic`)
- Свой jsonl файл
- Свой watcher task
- Свой message_thread_id при отправке

```
thread A message → tmux A → jsonl A → watcher A → send to thread A ONLY
thread B message → tmux B → jsonl B → watcher B → send to thread B ONLY
```

## Session Binding

### Проблема

`history.jsonl` содержит только последний session_id для cwd:
```json
{"project": "/path/to/project", "sessionId": "abc123"}
```

Нет информации о thread_id! При multi-session любой thread может "украсть" сессию другого.

### Решение: find_session_by_user_message

Вместо поиска по history.jsonl, сканируем ВСЕ jsonl файлы:

```python
def find_session_by_user_message(cwd: str, message: str) -> tuple[str, Path] | None:
    """Find session where last user message matches."""
    project_dir = compute_project_dir(cwd)

    # Scan ALL jsonl files, newest first
    for jsonl_path in sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        last_user_msg = extract_last_user_message(jsonl_path)
        if last_user_msg == message:
            session_id = jsonl_path.stem
            return (session_id, jsonl_path)

    return None
```

### Binding flow

```python
# poll_for_session_thread()
while not found:
    result = find_session_by_user_message(project.cwd, thread.last_sent_message)
    if result:
        session_id, jsonl_path = result
        thread.session_id = session_id
        thread.jsonl_path = str(jsonl_path)
        # Start watcher for this thread
        break
    await asyncio.sleep(1)
```

**Преимущества:**
- Гарантирует привязку к сессии где сообщение реально существует
- Работает для thread_id=None так же как для thread_id=456
- Не зависит от порядка записей в history.jsonl
- Корректно работает с /new командой

## Watchers

### watch_thread_jsonl

Следит за jsonl файлом конкретного треда:

```python
async def watch_thread_jsonl(bot: Bot, project: ProjectState, thread: ThreadInfo):
    path = Path(thread.jsonl_path)
    chat_id = project.chat_id
    thread_id = thread.thread_id  # None for General, int for Topics

    async for entry in watch_jsonl(path):
        await send_entry_to_telegram(
            bot, chat_id, entry,
            message_thread_id=thread_id  # ← Always correct!
        )
```

### Инвариант

```
EVERY thread has its own watcher
EVERY watcher watches ONLY that thread's jsonl
EVERY watcher sends to the correct message_thread_id
NO shared watcher across threads
```

## Permission Poller

Опрашивает tmux для permission prompts (Y/n вопросы от Claude):

```python
async def permission_poller_for_thread(bot: Bot, project: ProjectState, thread: ThreadInfo):
    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)

    while True:
        output = tmux.capture_pane()
        if has_permission_prompt(output):
            await send_permission_buttons(
                bot, project.chat_id,
                message_thread_id=thread.thread_id  # ← Correct thread!
            )
        await asyncio.sleep(1)
```

## Tmux Sessions

### Naming Convention

| Thread | Tmux Session Name |
|--------|-------------------|
| General (thread_id=None) | `claude-{project_name}` |
| Topic "mystic" | `claude-{project_name}-mystic` |
| Topic "arcane" | `claude-{project_name}-arcane` |

### TmuxSession class

```python
@dataclass
class TmuxSession:
    name: str
    cwd: str

    def send(self, text: str) -> None:
        """Send text and press Enter."""
        subprocess.run(["tmux", "send-keys", "-t", self.name, "-l", "--", text])
        time.sleep(0.1)
        subprocess.run(["tmux", "send-keys", "-t", self.name, "Enter"])

    def exists(self) -> bool:
        result = subprocess.run(["tmux", "has-session", "-t", self.name], capture_output=True)
        return result.returncode == 0

    def capture_pane(self) -> str:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", self.name, "-p", "-S", "-"],
            capture_output=True, text=True
        )
        return result.stdout
```

## Config Format

```json
{
  "projects": {
    "my-project": {
      "chat_id": -1001234567890,
      "cwd": "/home/user/my-project",
      "threads": {
        "null": {"name": "main"},
        "456": {"name": "mystic"},
        "789": {"name": "arcane"}
      }
    }
  }
}
```

**Note:** `"null"` string представляет thread_id=None (General topic).
