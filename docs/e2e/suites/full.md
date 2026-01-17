# Full Test Suite

**Время:** ~30 минут
**Когда:** Перед релизом, полная проверка

## Тесты

Все тесты из Critical плюс:

### Start Edge Cases
| ID | Название | Файл |
|----|----------|------|
| TC-START-008 | /restart перезапуск | commands/start.md |
| TC-START-009 | /start no directory | commands/start.md |
| TC-START-010 | /start git clone flow | commands/start.md |
| TC-START-011 | /start multiple tmux choice | commands/start.md |

### Sessions Extended
| ID | Название | Файл |
|----|----------|------|
| TC-SESSIONS-003 | /clear resets session | commands/sessions.md |
| TC-SESSIONS-004 | /resume explicit resume | commands/sessions.md |

### Settings
| ID | Название | Файл |
|----|----------|------|
| TC-SETTINGS-002 | /settings shows info | commands/settings.md |
| TC-SETTINGS-003 | /auto_accept toggle | commands/settings.md |
| TC-SETTINGS-004 | /get_debug_ids | commands/settings.md |
| TC-SETTINGS-010 | /auto_accept circle indicators | commands/settings.md |
| TC-SETTINGS-011 | Settings button toggles auto_accept | commands/settings.md |
| TC-SETTINGS-012 | Settings button toggles verbose | commands/settings.md |
| TC-SETTINGS-013 | Settings button cycles mode | commands/settings.md |

### Error Handling
| ID | Название | Файл |
|----|----------|------|
| TC-ERROR-001 | tmux died (kill -9) | commands/errors.md |
| TC-ERROR-002 | invalid session_id | commands/errors.md |
| TC-ERROR-003 | deleted worktree | commands/errors.md |

### Bot Lifecycle
| ID | Название | Файл |
|----|----------|------|
| TC-LIFECYCLE-001 | Bot restart recovery | commands/lifecycle.md |
| TC-LIFECYCLE-002 | Config persistence | commands/lifecycle.md |

### Watcher Extended
| ID | Название | Файл |
|----|----------|------|
| TC-WATCHER-003 | Long output chunking | commands/watcher.md |
| TC-WATCHER-004 | Watcher starts for resumed session | commands/watcher.md |
| TC-WATCHER-005 | Watcher output after bot restart | commands/watcher.md |
| TC-WATCHER-006 | Tool call truncated (verbose=off) | commands/watcher.md |
| TC-WATCHER-007 | Tool call full (verbose=on) | commands/watcher.md |

### Permissions Extended
| ID | Название | Файл |
|----|----------|------|
| TC-PERMISSIONS-005 | Poller detects new folder prompt | commands/permissions.md |
| TC-PERMISSIONS-006 | Poller starts for resumed session | commands/permissions.md |
| TC-PERMISSIONS-011 | Permission truncated (verbose=off) | commands/permissions.md |
| TC-PERMISSIONS-012 | Permission full (verbose=on) | commands/permissions.md |
| TC-PERMISSIONS-013 | Auto-accept truncated (verbose=off) | commands/permissions.md |
| TC-PERMISSIONS-014 | Auto-accept full (verbose=on) | commands/permissions.md |

## Включённые тесты из Critical

Все 26 тестов из critical.md

## Критерий успеха

Все ~50 тестов PASS = готов к релизу.
