# Session Binder: Hooks-Based Approach (POSTPONED)

> **Status:** Отложен в пользу более простого подхода с Telegram командами
>
> **See instead:** [../2025-12-29-session-binder-design.md](../2025-12-29-session-binder-design.md)

## Почему этот подход был рассмотрен

При исследовании проблемы Thread Session Mixup мы искали способ узнать какой именно thread получил новую сессию при `/new` или `/clear`.

**Идея:** Claude Code поддерживает hooks (SessionStart), которые вызываются при старте сессии. Можно:
1. Настроить hook который отправляет HTTP запрос
2. В hook получить tmux session name через `tmux display-message`
3. Передать session_id + tmux_session в Codogram
4. Codogram привязывает сессию к правильному thread

## Почему отложен

### 1. Избыточная сложность

Требует:
- HTTP сервер (HookServer) в Codogram
- Shell скрипт (session_hook.sh)
- CLI для настройки hooks (setup_hooks.py)
- Модификация ~/.claude/settings.json пользователя
- Зависимость от aiohttp

### 2. Найден более простой подход

После исследования структуры файлов Claude Code выяснилось:

| Команда | Новая сессия? |
|---------|---------------|
| `/new` | ДА |
| `/clear` | ДА |
| `/compact` | НЕТ |

Если `/compact` не меняет session_id, то проблема только с `/new` и `/clear`. Эти команды можно выполнять **через Telegram бот**, и тогда бот **всегда знает** какой thread ждёт новую сессию.

### 3. User experience

- Hooks требуют настройки на стороне пользователя
- Telegram команды работают "из коробки"

## Связанные документы

- [Implementation Plan (hooks)](../../plans/alternative/2025-12-29-session-binder-hooks-implementation-plan.md) - детальный план реализации hooks подхода
- [Research: Claude Code File Structure](../../research/claude-code-file-structure.md) - исследование структуры файлов
- [Research: Thread Session Binding Analysis](../../research/thread-session-binding-analysis.md) - анализ всех подходов
- [Bug: Thread Session Mixup](../../bugs/2025-12-29-thread-session-mixup.md) - описание проблемы

## Когда может пригодиться

Этот подход может быть полезен если:
1. Нужна instant detection (без polling)
2. Пользователь делает `/new` напрямую в tmux (не через бота)
3. Нужна интеграция с другими Claude Code hooks

---

## Архитектура (для справки)

```
┌─────────────────────────────────────────────────────────────┐
│                         Claude                               │
│  (SessionStart hook → session_hook.sh → HTTP POST)          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    HookServer (adapter)                      │
│  - Слушает на порту HOOK_SERVER_PORT                        │
│  - Получает: session_id, cwd, tmux_session                  │
│  - Вызывает: session_binder.bind_from_hook()                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 SessionBinderService (service)               │
│  - bind_from_hook(): точная привязка через hook             │
│  - check_and_bind(): fallback через content matching        │
└─────────────────────────────────────────────────────────────┘
```

## Компоненты

### 1. HookServer (adapters/hook_server.py)

```python
"""HTTP server for receiving Claude session hooks."""

from aiohttp import web
from ..logging_config import logger


class HookServer:
    """Receives SessionStart hooks from Claude."""

    def __init__(self, port: int, on_session_hook):
        self.port = port
        self.on_session_hook = on_session_hook
        self._app = None
        self._runner = None

    async def start(self):
        """Start the HTTP server."""
        self._app = web.Application()
        self._app.router.add_post('/hook/session-start', self._handle_session_start)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, '127.0.0.1', self.port)
        await site.start()

        logger.info(f"hook_server_started: port={self.port}")

    async def stop(self):
        """Stop the HTTP server."""
        if self._runner:
            await self._runner.cleanup()

    async def _handle_session_start(self, request: web.Request) -> web.Response:
        """Handle SessionStart hook from Claude."""
        try:
            data = await request.json()

            session_id = data.get('session_id')
            cwd = data.get('cwd')
            tmux_session = data.get('tmux_session')

            if not session_id:
                return web.Response(text='missing session_id', status=400)

            await self.on_session_hook(session_id, cwd, tmux_session)

            return web.Response(text='ok')

        except Exception as e:
            logger.error(f"hook_error: {e}")
            return web.Response(text='error', status=500)
```

### 2. session_hook.sh

```bash
#!/bin/bash
# Claude Code SessionStart hook - sends session info to codogram

set -e

input=$(cat)
session_id=$(echo "$input" | jq -r '.session_id // empty')
cwd=$(echo "$input" | jq -r '.cwd // empty')

if [ -z "$session_id" ]; then
    exit 0
fi

tmux_session=$(tmux display-message -p '#S' 2>/dev/null || echo "")
HOOK_PORT="${CODOGRAM_HOOK_PORT:-8787}"

curl -s -X POST "http://127.0.0.1:${HOOK_PORT}/hook/session-start" \
    -H "Content-Type: application/json" \
    -d "{
        \"session_id\": \"$session_id\",
        \"cwd\": \"$cwd\",
        \"tmux_session\": \"$tmux_session\"
    }" >/dev/null 2>&1 || true

exit 0
```

### 3. ~/.claude/settings.json configuration

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "CODOGRAM_HOOK_PORT=8787 /path/to/session_hook.sh"
          }
        ]
      }
    ]
  }
}
```

## Content Matching Fallback

Для случаев когда hooks не настроены, был спроектирован fallback через content matching:

1. Читаем последнее сообщение assistant из session jsonl
2. Делаем `tmux capture-pane` для каждого unbound thread
3. Если контент совпадает → это наш thread

**Минусы:**
- Ненадёжно (контент может не совпадать)
- Медленно (нужно capture всех tmux panes)
- Сложная логика

---

## Changelog

- 2025-12-29: Moved to alternative/ - superseded by Telegram commands approach
- 2025-12-29 v3: Added hooks as primary mechanism
- 2025-12-29 v2: Added content matching fallback
- 2025-12-29 v1: Initial design
