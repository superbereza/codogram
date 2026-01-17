# Critical Test Suite

**Время:** ~15 минут
**Когда:** Перед мержем, после значительных изменений

## Тесты

| # | ID | Название | Файл |
|---|-----|----------|------|
| 1 | TC-START-001 | /start подключается к существующему tmux | commands/start.md |
| 2 | TC-START-002 | /start запускает Claude (нет tmux) | commands/start.md |
| 3 | TC-START-003 | /start в topic | commands/start.md |
| 4 | TC-START-004 | /start resume в General | commands/start.md |
| 5 | TC-START-005 | /start resume в Topic | commands/start.md |
| 6 | TC-START-006 | /start resume в Branch | commands/start.md |
| 7 | TC-START-007 | session_id сохраняется при kill tmux | commands/start.md |
| 8 | TC-MESSAGES-001 | Сообщение доходит до Claude | commands/messages.md |
| 9 | TC-MESSAGES-002 | Сообщение изолировано (не в других threads) | commands/messages.md |
| 10 | TC-WATCHER-001 | Tool call появляется в правильном topic | commands/watcher.md |
| 11 | TC-WATCHER-002 | Tool call НЕ появляется в других topics | commands/watcher.md |
| 12 | TC-PERMISSIONS-001 | Permission кнопки в правильном topic | commands/permissions.md |
| 13 | TC-PERMISSIONS-002 | Permission кнопки НЕ в других topics | commands/permissions.md |
| 14 | TC-PERMISSIONS-003 | Клик работает | commands/permissions.md |
| 15 | TC-PERMISSIONS-004 | auto_accept работает | commands/permissions.md |
| 16 | TC-SESSIONS-001 | /new создаёт новую сессию | commands/sessions.md |
| 17 | TC-SESSIONS-002 | /esc отменяет запрос | commands/sessions.md |
| 18 | TC-THREADS-001 | /thread создаёт topic | commands/threads.md |
| 19 | TC-BRANCHES-001 | /branch создаёт worktree + topic | commands/branches.md |
| 20 | TC-FINISH-001 | /finish archive topic | commands/finish.md |
| 21 | TC-FINISH-002 | /finish merge branch | commands/finish.md |
| 22 | TC-SETTINGS-002 | /settings показывает session state | commands/settings.md |
| 23 | TC-SETTINGS-005 | /shift_tab переключает mode | commands/settings.md |
| 24 | TC-PERMISSIONS-010 | Message cancels permission prompt | commands/permissions.md |
| 25 | TC-SETTINGS-008 | /settings новый формат с inline кнопками | commands/settings.md |
| 26 | TC-SETTINGS-009 | /verbose toggle | commands/settings.md |

## Подготовка

```bash
# Бот запущен
./restart.sh

# Тестовый репозиторий существует
cd /tmp/test-branch-repo && git status

# Для topic тестов - нужны существующие topics
# Создай через /thread или /branch если нет
```

## Критерий успеха

Все 26 тестов PASS = основной функционал работает, регрессий нет.
