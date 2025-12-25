# Start Claude from Telegram - Design Draft

**Status:** In Progress (brainstorming)

## Цель

Запуск Claude сессии из Telegram по команде /start, вместо текущего flow где Claude запускается вручную.

## Текущий flow

1. Пользователь вручную запускает tmux + claude
2. SessionStart hook регистрирует сессию в боте
3. Бот начинает следить за сессией

## Желаемый flow

1. Пользователь отправляет /start в Telegram чате проекта
2. Бот находит путь к проекту
3. Бот запускает tmux сессию с Claude
4. SessionStart hook регистрирует сессию
5. Бот подключается к сессии

## Решения

### Определение пути к проекту

**Выбрано:** Конвенция + fallback

1. По умолчанию: `~/dev/{project_name}`
2. Если директория не существует — использовать путь из `/register_dir`
3. `/register_dir` позволяет переопределить путь

**Будущее:** возможность создать директорию + git clone/init

### Именование tmux сессий

**Выбрано:** `claude-{project_name}`

Примеры:
- `claude-personal-agent`
- `claude-bz-merch-assistant`

### Логика запуска

**Выбрано:** Гибрид

1. Проверить существует ли tmux сессия `claude-{project}`
2. Если нет — создать новую и запустить claude
3. Если есть — не трогать существующую, создать новую (чтобы не мешать работе пользователя)

### Определение что Claude работает

**Выбрано:** Доверять регистрации + tmux has-session

```python
def is_claude_running(project_name):
    session = get_session_by_project(project_name)
    if not session or not session.poller_task:
        return False
    tmux_exists = run(["tmux", "has-session", "-t", f"claude-{project_name}"])
    return tmux_exists.returncode == 0 and not session.poller_task.done()
```

**Почему не pgrep:**
- Сложнее (парсить pane_tty)
- Редкий edge case не стоит усложнения

**Почему не проверка экрана:**
- Экран пустой когда Claude думает
- Хрупко, зависит от формата вывода

## Открытые вопросы

- [ ] Что показывать в /start если Claude уже работает?
- [ ] Нужна ли команда /stop для остановки Claude?
- [ ] Как обрабатывать ошибки запуска (нет директории, нет claude, etc)?

## Будущие улучшения

- Создание директории по конвенции + git clone/init
- Heartbeat для определения что Claude жив
- /stop команда
