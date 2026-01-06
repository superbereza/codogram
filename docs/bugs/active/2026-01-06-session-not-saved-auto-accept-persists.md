# Session not saved + auto_accept persists unexpectedly

**Найден:** markdown-fix thread in codogram chat
**Severity:** major (session binding broken for external worktrees)
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

### Root Cause

**History watcher ищет сессии не в той директории!**

`history_watcher.py:_bind_awaiting_threads()` использует `project.cwd` для поиска сессий:
```python
project_dir = self._get_project_sessions_dir(project.cwd)
# Ищет в: ~/.claude/projects/-home-superbereza-dev-codogram/
```

Но Claude в worktree создаёт сессию в директории worktree:
```
~/.claude/projects/-home-superbereza-dev-codogram-markdown-fix/7c2f5cff-....jsonl
```

**Watcher не видит сессию, потому что ищет не там!**

### Фикс

В `_bind_awaiting_threads` для тредов с `worktree_path` нужно искать сессии в директории worktree:

```python
# Determine which directory to search
if thread.worktree_path:
    search_dir = self._get_project_sessions_dir(thread.worktree_path)
else:
    search_dir = self._get_project_sessions_dir(project.cwd)
```

### Affected

Любой тред с worktree в отдельной директории (не `.worktrees/` внутри project.cwd)

## Проблема 2: auto_accept сохраняется между запусками

Thread имел `auto_accept: true` с предыдущей сессии.
При /start Claude спросил "Do you trust files in this folder?" и бот авто-акцептнул.

### Текущее поведение
auto_accept сохраняется в config и применяется к новым сессиям.

### Предложение пользователя
Сбрасывать auto_accept при /start или делать его per-session (не persistent).

### Альтернатива
Оставить как есть, но документировать что auto_accept постоянный для треда.
