# Claude Code File Structure Research

> Исследование структуры файлов Claude Code для интеграции с Codogram

## ~/.claude/ Directory

```
~/.claude/
├── .credentials.json          # OAuth credentials
├── .claude.json               # MCP servers, preferences, caches
├── settings.json              # User settings, permissions, hooks
├── CLAUDE.md                  # User-level memory/instructions
├── history.jsonl              # Master session log (ALL projects)
├── stats-cache.json           # Usage statistics cache
│
├── projects/                  # Project-specific session files
│   └── {project_hash}/        # Hash = normalized cwd with "/" → "-"
│       ├── {session_id}.jsonl # Session conversation history
│       └── ...
│
├── agents/                    # Custom subagent definitions (*.md)
├── debug/                     # Debug logs
├── downloads/                 # Downloaded files
├── file-history/              # File change history
├── plans/                     # Agent plans
├── plugins/                   # Installed plugins
├── session-env/               # Session environment files
├── shell-snapshots/           # Shell state snapshots
├── statsig/                   # Feature flags
├── telemetry/                 # Telemetry data
└── todos/                     # Todo lists
```

## history.jsonl

**Location:** `~/.claude/history.jsonl`

**Purpose:** Master log - запись о каждом сообщении пользователя во всех проектах и сессиях.

**Format:** JSONL (один JSON объект на строку)

### Структура записи

```json
{
  "display": "текст сообщения пользователя",
  "pastedContents": {},
  "timestamp": 1767043487392,
  "project": "/home/user/dev/myproject",
  "sessionId": "dc98e032-0d7f-4e3a-88aa-3752d3fbc88e"
}
```

### Ключевые поля

| Поле | Описание |
|------|----------|
| `display` | Текст сообщения пользователя (включая команды) |
| `timestamp` | Unix timestamp в миллисекундах |
| `project` | Абсолютный путь к проекту (cwd) |
| `sessionId` | UUID текущей сессии |
| `pastedContents` | Вставленный контент (если есть) |

### Важно для Codogram

- **НЕ содержит** информацию о tmux сессии
- **НЕ содержит** parentSessionId (нет связи между сессиями)
- Можно отслеживать смену `sessionId` для того же `project`
- Используется для `find_session_for_project(cwd)` - поиск последней сессии

---

## Session JSONL Files

**Location:** `~/.claude/projects/{project_hash}/{session_id}.jsonl`

**Project hash formula:**
```
/home/user/dev/myproject → -home-user-dev-myproject
```

### Типы записей

#### 1. file-history-snapshot
```json
{
  "type": "file-history-snapshot",
  "messageId": "698fdd98-889c-4d94-a29e-a52dc58c7f1a",
  "snapshot": {
    "messageId": "...",
    "trackedFileBackups": {},
    "timestamp": "2025-12-29T21:22:22.376Z"
  }
}
```

#### 2. user message
```json
{
  "type": "user",
  "parentUuid": "ab2380e8-a781-48b5-ba05-0901bc22a2b5",
  "uuid": "698fdd98-889c-4d94-a29e-a52dc58c7f1a",
  "sessionId": "dc98e032-0d7f-4e3a-88aa-3752d3fbc88e",
  "cwd": "/home/user/dev/myproject",
  "timestamp": "2025-12-29T21:22:22.034Z",
  "message": {
    "role": "user",
    "content": "текст сообщения"
  }
}
```

#### 3. assistant message
```json
{
  "type": "assistant",
  "parentUuid": "bc0cbd1d-ec58-4076-ac6e-3924b4302886",
  "uuid": "be21c3f8-c712-4797-87fc-2e14703aebf1",
  "sessionId": "dc98e032-0d7f-4e3a-88aa-3752d3fbc88e",
  "timestamp": "2025-12-29T21:24:59.217Z",
  "message": {
    "role": "assistant",
    "model": "claude-opus-4-5-20251101",
    "content": [
      {"type": "text", "text": "..."},
      {"type": "tool_use", "name": "Bash", "input": {...}}
    ]
  }
}
```

#### 4. summary (после /compact)
```json
{
  "type": "summary",
  "summary": "Brief description of conversation",
  "leafUuid": "322b0b9d-99d8-4aaa-8a1f-05645dcb6cbe"
}
```

### Важные поля

| Поле | Описание |
|------|----------|
| `parentUuid` | UUID предыдущего сообщения в цепочке (НЕ родительская сессия!) |
| `uuid` | UUID этого сообщения |
| `sessionId` | ID сессии (совпадает с именем файла) |
| `type` | `user`, `assistant`, `summary`, `file-history-snapshot` |

### Важно для Codogram

- `parentUuid` ссылается на сообщение в **той же сессии**, не на родительскую сессию
- **Нет способа** связать новую сессию с предыдущей (нет parentSessionId)
- `summary` записи появляются при `/compact` **внутри той же сессии**

---

## Поведение команд

| Команда | Новая сессия? | Новый файл? | Что происходит |
|---------|---------------|-------------|----------------|
| `/new` | ДА | ДА | Создаётся новый {session_id}.jsonl |
| `/clear` | ДА | ДА | Создаётся новый {session_id}.jsonl |
| `/compact` | НЕТ | НЕТ | Добавляется `summary` запись в текущий файл |
| `/resume <id>` | НЕТ | НЕТ | Продолжает существующую сессию |

### Как определить что произошло

1. **Смена sessionId в history.jsonl** → был `/new` или `/clear`
2. **Появление `summary` записи** → был `/compact`
3. **Первая запись с `parentUuid: null`** → начало новой сессии

---

## settings.json

**Locations (в порядке приоритета):**
1. Enterprise: `/etc/claude-code/managed-settings.json`
2. Project local: `.claude/settings.local.json`
3. Project: `.claude/settings.json`
4. User: `~/.claude/settings.json`

### Структура hooks

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/script.sh",
            "timeout": 30
          }
        ]
      }
    ],
    "SessionEnd": [...],
    "PreToolUse": [...],
    "PostToolUse": [...],
    "UserPromptSubmit": [...],
    "Notification": [...],
    "Stop": [...],
    "SubagentStop": [...],
    "PreCompact": [...]
  }
}
```

### Доступные hooks

| Hook | Trigger | Matcher |
|------|---------|---------|
| `SessionStart` | Сессия стартует/resume | `startup`, `resume`, `clear`, `compact` |
| `SessionEnd` | Сессия завершается | - |
| `PreToolUse` | Перед вызовом инструмента | tool name |
| `PostToolUse` | После вызова инструмента | tool name |
| `UserPromptSubmit` | Пользователь отправил сообщение | - |
| `Notification` | Уведомление | `permission_prompt`, `idle_prompt` |
| `Stop` | Агент завершил ответ | - |
| `PreCompact` | Перед compact | `manual`, `auto` |

### Hook input (stdin)

```json
{
  "session_id": "abc123-def456-...",
  "cwd": "/path/to/project",
  "transcript_path": "~/.claude/projects/.../session.jsonl",
  "hook_event_name": "SessionStart",
  "tool_name": "Write",
  "tool_input": {...}
}
```

### Hook output (stdout)

```json
{
  "decision": "allow|deny|block",
  "reason": "explanation",
  "continue": true
}
```

---

## Для Codogram: ключевые выводы

### Что можно использовать

1. **history.jsonl polling** - обнаружение последней сессии для проекта
2. **Session jsonl files** - мониторинг сообщений Claude
3. **SessionStart hook** - получение session_id + cwd (но НЕ tmux session!)

### Ограничения

1. **Нет tmux session** в данных Claude Code
2. **Нет parentSessionId** - нельзя связать сессии
3. **history.jsonl** содержит только user messages, не assistant
4. **Нет информации** о том какой thread породил сессию

### Рекомендуемый подход

Поскольку Claude Code не знает о tmux sessions, привязка thread↔session должна происходить через:

1. **Telegram команды** (`/new`, `/clear`) → бот знает какой thread
2. **Флаг `awaiting_new_session`** → ждём новую сессию для этого thread
3. **history.jsonl polling** → обнаружение новой сессии
4. **Привязка** к thread который ждал

---

## Changelog

- 2025-12-29: Initial research based on experiments and documentation
