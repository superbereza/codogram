# Multi-Session Architecture Design

## Overview

Переход от одного захардкоженного чата к архитектуре где:
- Один процесс бота обслуживает несколько Claude сессий
- Каждый проект = отдельная Telegram группа
- Сессии регистрируются через Claude Code hooks

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                    codogram                       │
│                    (один процесс)                        │
├─────────────────────────────────────────────────────────┤
│  HTTP Server :8787                                       │
│    POST /session/register                                │
│    POST /session/unregister                              │
│                                                          │
│  Session Manager                                         │
│    sessions: Map<session_id, SessionState>               │
│    project_to_chat: Map<project_name, chat_id>           │
│                                                          │
│  Per-session tasks:                                      │
│    - Permission Poller (tmux → Telegram)                 │
│    - Watcher (jsonl → Telegram)                          │
│                                                          │
│  Telegram Bot (aiogram)                                  │
│    - Роутинг сообщений по chat_id → session              │
│    - /register_dir команда                               │
└─────────────────────────────────────────────────────────┘
         ▲                              │
         │ HTTP                         │ Telegram API
         │                              ▼
┌────────┴────────┐           ┌─────────────────┐
│  Claude Code    │           │  Telegram       │
│  SessionStart   │           │  Groups         │
│  SessionEnd     │           │  (per project)  │
│  hooks          │           └─────────────────┘
└─────────────────┘
```

## Регистрация сессий

### Claude Code hooks

```json
// ~/.claude/settings.json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "/path/to/hooks/session-start.sh"
      }]
    }],
    "SessionEnd": [{
      "hooks": [{
        "type": "command",
        "command": "/path/to/hooks/session-end.sh"
      }]
    }]
  }
}
```

### session-start.sh

1. Читает JSON с `session_id`, `cwd`
2. Определяет `tmux_session` через `tmux display-message -p '#S'`
3. POST на `localhost:8787/session/register`

### session-end.sh

1. Читает JSON с `session_id`, `reason`
2. POST на `localhost:8787/session/unregister`

### Session Manager при регистрации

1. Получает `{session_id, cwd, tmux_session}`
2. Вычисляет `project_name` из `cwd` (с учётом worktree)
3. Ищет `chat_id` по маппингу
4. Если найден — создаёт poller + watcher tasks
5. Если нет — сессия работает без Telegram

## Определение project_name

```python
def get_project_name(cwd: Path) -> str:
    """
    Возвращает имя проекта для привязки к чату.
    Worktree → основной репозиторий.
    """
    git_path = cwd / ".git"

    # Worktree: .git это файл с gitdir
    if git_path.is_file():
        content = git_path.read_text().strip()
        # gitdir: /dev/personal-agent/.git/worktrees/feature-x
        if content.startswith("gitdir:"):
            gitdir = Path(content.split(":", 1)[1].strip())
            # .git/worktrees/xxx → .git → repo folder
            main_repo = gitdir.parent.parent.parent
            return main_repo.name

    # Обычный репо или нет git — имя папки
    return cwd.name
```

| cwd | .git | project_name |
|-----|------|--------------|
| `/dev/personal-agent` | нет | `personal-agent` |
| `/dev/personal-agent` | папка | `personal-agent` |
| `/dev/personal-agent-feature` | файл→gitdir | `personal-agent` |

## Маппинг project → chat

### Хранение

```
agent-tools/codogram/.config.json

{
  "projects": {
    "personal-agent": 12345678,
    "other-project": -100987654321
  },
  "sessions": {
    "76821652-...": {
      "tmux_session": "personal-agent",
      "cwd": "/home/superbereza/dev/personal-agent",
      "project_name": "personal-agent",
      "jsonl_path": "~/.claude/projects/.../76821652-....jsonl"
    }
  }
}
```

### Автоматическая регистрация

1. Бот добавляется в группу "personal-agent"
2. При любом сообщении бот читает `message.chat.title`
3. Если `title` нет в маппинге — добавляет `{title: chat_id}`
4. Сохраняет JSON

### Ручная регистрация

```
/register_dir custom-path
```

Регистрирует `chat_id` текущего чата для `{base_dir}/custom-path`

## Конфигурация

### .env

```bash
TELEGRAM_TOKEN=123456:ABC...
BASE_DIR=/home/superbereza/dev
ADMIN_CHAT_ID=12345678  # личный чат для алертов
```

### .config.json

```json
{
  "projects": {
    "personal-agent": 12345678
  },
  "sessions": {}
}
```

При старте бота — восстанавливаем poller/watcher для всех сохранённых сессий.

## Роутинг сообщений

### Telegram → Claude

1. Сообщение приходит в группу `chat_id=12345678`
2. Бот ищет активную сессию для этого `chat_id`
3. Если найдена — отправляет в соответствующую tmux сессию
4. Если нет активной сессии — отвечает "No active session"

### Claude → Telegram

1. Poller/Watcher видит событие в сессии
2. Сессия знает свой `project_name`
3. По маппингу находит `chat_id`
4. Отправляет в нужную группу

### Error handling

1. Сообщение в группу где нет сессии → ответ "No active session" в эту группу
2. Claude событие, но нет маппинга для project → алерт в ADMIN_CHAT_ID
3. Ошибка отправки в группу → алерт в ADMIN_CHAT_ID

## Команды

- `/register_dir <path>` — привязать чат к папке
- `/status` — показать активную сессию (если есть)

## Структура файлов

```
agent-tools/codogram/
├── .env                      # TELEGRAM_TOKEN, BASE_DIR, ADMIN_CHAT_ID
├── .config.json              # projects + sessions (gitignored)
├── .gitignore                # .env, .config.json
├── hooks/
│   ├── session-start.sh      # → POST /session/register
│   └── session-end.sh        # → POST /session/unregister
├── src/codogram/
│   ├── main.py               # HTTP server + Telegram bot
│   ├── config.py             # загрузка .env + .config.json
│   ├── session_manager.py    # регистрация, персистенция
│   ├── project_resolver.py   # get_project_name (worktree logic)
│   ├── permission_poller.py  # (существующий, адаптировать)
│   ├── watcher.py            # (существующий, адаптировать)
│   ├── bot.py                # handlers, роутинг
│   └── tmux.py               # (существующий)
└── restart.sh
```
