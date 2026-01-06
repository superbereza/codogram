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

### Возможные причины
- Прошлый /start не привязал сессию
- session_id был сброшен

### Improvement
При /start если session_id=null но есть jsonl файлы для этого cwd:
- Показать список найденных сессий
- Предложить привязать одну из них

## Проблема 2: auto_accept сохраняется между запусками

Thread имел `auto_accept: true` с предыдущей сессии.
При /start Claude спросил "Do you trust files in this folder?" и бот авто-акцептнул.

### Текущее поведение
auto_accept сохраняется в config и применяется к новым сессиям.

### Предложение пользователя
Сбрасывать auto_accept при /start или делать его per-session (не persistent).

### Альтернатива
Оставить как есть, но документировать что auto_accept постоянный для треда.
