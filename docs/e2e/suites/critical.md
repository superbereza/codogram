# Critical Test Suite

**Время:** ~25 минут
**Когда:** Перед мержем, после значительных изменений

## Тесты

### Setup Flow v2

| # | ID | Название | Файл |
|---|-----|----------|------|
| 1 | TC-SETUP-001 | Setup flow triggers on /start in new chat | commands/setup.md |
| 2 | TC-SETUP-002 | Admin rights check flow | commands/setup.md |
| 3 | TC-SETUP-003 | Clone flow - valid URL | commands/setup.md |
| 4 | TC-SETUP-004 | Clone flow - invalid URL | commands/setup.md |
| 5 | TC-SETUP-005 | Connect flow - folder selection | commands/setup.md |
| 6 | TC-SETUP-006 | New project flow - suggested name | commands/setup.md |
| 7 | TC-SETUP-007 | New project flow - custom name | commands/setup.md |
| 8 | TC-SETUP-008 | Git choice - Init | commands/setup.md |
| 9 | TC-SETUP-010 | Command blocked during setup | commands/setup.md |
| 10 | TC-SETUP-011 | /start restarts setup during active flow | commands/setup.md |
| 11 | TC-SETUP-012 | BASE_DIR not configured | commands/setup.md |
| 12 | TC-SETUP-023 | /reset_all cancels setup | commands/setup.md |

### Start/Resume Flow

| # | ID | Название | Файл |
|---|-----|----------|------|
| 13 | TC-START-001 | /start подключается к существующему tmux | commands/start.md |
| 14 | TC-START-002 | /start запускает Claude (нет tmux) | commands/start.md |
| 15 | TC-START-003 | /start в topic | commands/start.md |
| 16 | TC-START-004 | /start resume в General | commands/start.md |
| 17 | TC-START-005 | /start resume в Topic | commands/start.md |
| 18 | TC-START-006 | /start resume в Branch | commands/start.md |
| 19 | TC-START-007 | session_id сохраняется при kill tmux | commands/start.md |

### Messages & Tools

| # | ID | Название | Файл |
|---|-----|----------|------|
| 20 | TC-MESSAGES-001 | Сообщение доходит до Claude | commands/messages.md |
| 21 | TC-MESSAGES-002 | Сообщение изолировано (не в других threads) | commands/messages.md |
| 22 | TC-WATCHER-001 | Tool call появляется в правильном topic | commands/watcher.md |
| 23 | TC-WATCHER-002 | Tool call НЕ появляется в других topics | commands/watcher.md |

### Permissions

| # | ID | Название | Файл |
|---|-----|----------|------|
| 24 | TC-PERMISSIONS-001 | Permission кнопки в правильном topic | commands/permissions.md |
| 25 | TC-PERMISSIONS-002 | Permission кнопки НЕ в других topics | commands/permissions.md |
| 26 | TC-PERMISSIONS-003 | Клик работает | commands/permissions.md |
| 27 | TC-PERMISSIONS-004 | auto_accept работает | commands/permissions.md |
| 28 | TC-PERMISSIONS-010 | Message cancels permission prompt | commands/permissions.md |

### Sessions & Commands

| # | ID | Название | Файл |
|---|-----|----------|------|
| 29 | TC-SESSIONS-001 | /clear_context создаёт новую сессию | commands/sessions.md |
| 30 | TC-SESSIONS-002 | /esc отменяет запрос | commands/sessions.md |
| 31 | TC-NEWCHAT-001 | /new_chat shows context + choice | commands/new_chat.md |
| 32 | TC-NEWCHAT-004 | Magic name creates chat | commands/new_chat.md |
| 33 | TC-FINISHCHAT-001 | /finish_chat archives topic | commands/finish_chat.md |
| 34 | TC-FINISHCHAT-002 | /finish_chat merges branch | commands/finish_chat.md |

### Settings

| # | ID | Название | Файл |
|---|-----|----------|------|
| 35 | TC-SETTINGS-002 | /settings показывает session state | commands/settings.md |
| 36 | TC-SETTINGS-005 | /shift_tab переключает mode | commands/settings.md |
| 37 | TC-SETTINGS-008 | /settings новый формат с inline кнопками | commands/settings.md |
| 38 | TC-SETTINGS-009 | /verbose toggle | commands/settings.md |

### Avatar Pack

| # | ID | Название | Файл |
|---|-----|----------|------|
| 39 | TC-AVATAR-001 | /exp_avatar_pack create prompt (OFF) | commands/avatar_pack.md |
| 40 | TC-AVATAR-002 | Create avatar pack via button | commands/avatar_pack.md |
| 41 | TC-AVATAR-003 | /exp_avatar_pack disable prompt (ON) | commands/avatar_pack.md |
| 42 | TC-AVATAR-005 | Disable avatar pack via button | commands/avatar_pack.md |
| 43 | TC-AVATAR-006 | /settings shows avatar_pack status | commands/avatar_pack.md |
| 44 | TC-AVATAR-007 | Topic launch shows emoji hint | commands/avatar_pack.md |

## Подготовка

```bash
# Бот запущен
./stop-and-restart.sh

# Тестовый репозиторий существует
cd /tmp/test-branch-repo && git status

# Для topic тестов - нужны существующие topics
# Создай через /thread или /branch если нет

# Для setup тестов - нужен чат без зарегистрированного проекта
# Или используй /reset_all для очистки
```

## Критерий успеха

Все 44 теста PASS = основной функционал работает, регрессий нет.
