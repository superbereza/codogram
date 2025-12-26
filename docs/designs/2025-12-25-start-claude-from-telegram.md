# Start Claude from Telegram - Design

**Status:** Restored (2025-12-26)

## Цель

Запуск Claude сессии из Telegram по команде /start, вместо текущего flow где Claude запускается вручную.

## Flow

### /start в чате проекта

```
┌─────────────────────────────────────────────────────────────┐
│                         /start                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │ Есть активная сессия?  │
                 │ (config + poller_running)│
                 └────────────────────────┘
                      │            │
                     да           нет
                      │            │
                      ▼            ▼
              ┌──────────┐  ┌─────────────────┐
              │ Показать │  │ Путь к проекту  │
              │ статус   │  │ ~/dev/{project} │
              └──────────┘  └─────────────────┘
                                   │
                                   ▼
                      ┌────────────────────────┐
                      │ Директория существует? │
                      └────────────────────────┘
                           │            │
                          да           нет
                           │            │
                           ▼            ▼
                   ┌──────────┐  ┌─────────────────┐
                   │ Запустить│  │ Спросить:       │
                   │ Claude   │  │ Создать/Указать │
                   └──────────┘  └─────────────────┘
```

### Директория не существует

**Сообщение:**
```
Директория ~/dev/{project} не найдена.

[Создать]  [Указать другую]
```

**Создать → Git setup:**
```
Настроить гит?

[init локально]  [init + gh create]  [git clone]
нет
```

- `init локально` → `git init`
- `init + gh create` → спросить public/private → `git init && gh repo create`
- `git clone` → спросить URL → `git clone <url> .`
- `нет` → пропустить

**git clone — запрос URL:**
```
Отправь ссылку на репозиторий:
• SSH: git@github.com:user/repo.git
• HTTPS: https://github.com/user/repo.git
```

**init + gh create — public/private:**
```
Видимость репозитория?

[Private]  [Public]
```

**Указать другую:**
```
Отправь путь к директории проекта:
```
→ сохранить в config → продолжить запуск

### Запуск Claude

1. Создать tmux сессию: `tmux new-session -d -s claude-{project} -c {path}`
2. Отправить команду: `tmux send-keys -t claude-{project} "claude" Enter`
3. SessionStart hook автоматически зарегистрирует сессию
4. Показать: "Claude запущен в claude-{project}"

### Ошибки

Любые ошибки (tmux, gh, git, etc.) → сообщение в чат:
```
Ошибка запуска: {детали ошибки}
```

## Технические решения

### Именование tmux сессий

Формат: `claude-{project_name}`

Примеры:
- `claude-personal-agent`
- `claude-bz-merch-assistant`

### Определение пути к проекту

1. Проверить `~/dev/{project_name}`
2. Если нет — проверить сохранённый путь в config
3. Если нет — спросить (создать/указать)

### Определение что Claude работает

```python
def is_claude_running(project_name):
    session = get_session_by_project(project_name)
    if not session:
        return False
    tmux_exists = run(["tmux", "has-session", "-t", f"claude-{project_name}"])
    return tmux_exists.returncode == 0 and session.poller_task and not session.poller_task.done()
```

### Config расширение

```json
{
  "projects": {
    "personal-agent": {
      "chat_id": -5077677938,
      "path": "/home/user/dev/personal-agent"  // опционально, если не ~/dev/{name}
    }
  }
}
```

## Удаляемые команды

- `/register_dir` — функциональность встроена в /start flow

## Будущие улучшения

- /stop команда для остановки Claude
- Heartbeat для определения что Claude жив
- Выбор модели при запуске (opus/sonnet)
