# Smoke Test Suite

**Время:** ~2 минуты
**Когда:** Продакшн проверка "бот жив?"

## Тесты

| # | ID | Название | Файл |
|---|-----|----------|------|
| 1 | TC-SETTINGS-001 | /help отвечает | commands/settings.md |
| 2 | TC-START-001 | /start подключается к tmux | commands/start.md |
| 3 | TC-MESSAGES-001 | Сообщение доходит до Claude | commands/messages.md |
| 4 | TC-WATCHER-001 | Tool call появляется | commands/watcher.md |
| 5 | TC-PERMISSIONS-001 | Permission кнопки появляются | commands/permissions.md |

## Подготовка

```bash
# Убедись что бот запущен
./stop-and-restart.sh

# Убедись что есть tmux сессия
tmux new-session -d -s claude-codogram-testing-area -c /tmp/test-branch-repo
```

## Критерий успеха

Все 5 тестов PASS = бот работает, можно использовать.
