# Session not saved + auto_accept persists unexpectedly

**Найден:** markdown-fix thread in codogram chat
**Severity:** minor
**Status:** active

## Проблема 1: Сессия не сохранилась

Thread markdown-fix имеет:
- `session_id: null`
- `jsonl_path: null`
- Но jsonl существует: `~/.claude/projects/-home-superbereza-dev-codogram-markdown-fix/7c2f5cff-....jsonl`

При /start не предложился resume, потому что config не знает о сессии.

### Где хранится session_id

В `.config.json` → `projects.PROJECT.threads.TOPIC_ID.session_id`

Для markdown-fix (topic 8324):
```json
"session_id": null,
"jsonl_path": null,
"worktree_path": "/home/superbereza/dev/codogram-markdown-fix"
```

При этом другие worktree-треды имеют session_id (222, 260, 283).

### Возможные причины

1. Binding не дождался session_id из jsonl
2. Worktree в отдельной директории (не `.worktrees/`) обрабатывается иначе
3. Баг в предыдущей версии кода, уже пофикшен

### TODO

Проверить код binding для worktree в отдельной директории vs `.worktrees/`

## Проблема 2: auto_accept сохраняется между запусками

Thread имел `auto_accept: true` с предыдущей сессии.
При /start Claude спросил "Do you trust files in this folder?" и бот авто-акцептнул.

### Текущее поведение
auto_accept сохраняется в config и применяется к новым сессиям.

### Предложение пользователя
Сбрасывать auto_accept при /start или делать его per-session (не persistent).

### Альтернатива
Оставить как есть, но документировать что auto_accept постоянный для треда.
