# Poller Refactoring

**Date:** 2026-01-21
**Status:** Done

## Summary

Рефакторинг permission_poller.py (500+ строк) в модульную структуру с отдельными processors.

## Problem

`permission_poller.py` — монолитный файл на 500+ строк с одной god-function. Сложно добавлять новые фичи, тестировать, поддерживать.

## Solution

Разбить на пакет `claude/poller/` с отдельными processors по ответственностям.

### Файловая структура

```
src/codogram/claude/poller/
├── __init__.py          # re-export create_poller_task, create_poller_task_for_thread
├── context.py           # PollerContext dataclass
├── base.py              # BaseProcessor class
├── crash.py             # detect_crash() function
├── poller.py            # main loop
└── processors/
    ├── __init__.py
    ├── compact.py       # CompactProcessor (~20 строк)
    ├── thinking.py      # ThinkingProcessor (~50 строк)
    ├── suggestions.py   # SuggestionsProcessor (~40 строк)
    ├── stuck.py         # StuckProcessor (~35 строк)
    ├── permissions.py   # PermissionProcessor (~150 строк)
    └── ask_user.py      # AskUserQuestionProcessor (~80 строк)
```

### PollerContext

```python
@dataclass
class PollerContext:
    bot: Bot
    project: ProjectState
    thread: ThreadInfo | None
    tmux: TmuxSession
    queue: TelegramQueue
    chat_id: int
    thread_id: int | None
    log_prefix: str
    context_name: str
    tmux_name: str
```

### BaseProcessor

```python
class BaseProcessor:
    def __init__(self, ctx: PollerContext):
        self.ctx = ctx

    async def process(self, screen: str) -> None:
        raise NotImplementedError

    # Helpers
    async def send(self, text: str, **kwargs) -> list[int]: ...
    async def send_nowait(self, text: str, **kwargs) -> None: ...
    async def edit_by_key(self, text: str, key: str) -> None: ...
    async def delete_by_key(self, key: str) -> None: ...
    def log_debug(self, msg: str) -> None: ...
    def log_info(self, msg: str) -> None: ...
    def log_warning(self, msg: str) -> None: ...
```

### Main loop

```python
async def permission_poller(...) -> None:
    ctx = PollerContext(...)

    processors = [
        CompactProcessor(ctx),
        ThinkingProcessor(ctx),
        SuggestionsProcessor(ctx),
        StuckProcessor(ctx),
        PermissionProcessor(ctx),
        AskUserQuestionProcessor(ctx),
    ]

    while True:
        await asyncio.sleep(settings.permission_poller_interval)

        screen = ctx.tmux.capture_pane()

        if crash := detect_crash(screen):
            await notify_crash(ctx, crash)
            return

        for processor in processors:
            await processor.process(screen)
```

### Processors

| Processor | Ответственность |
|-----------|-----------------|
| CompactProcessor | Уведомление о начале compacting |
| ThinkingProcessor | Отображение статуса thinking |
| SuggestionsProcessor | Input suggestions как ReplyKeyboard |
| StuckProcessor | Детекция застрявших сообщений |
| PermissionProcessor | Permission prompts с state machine |
| AskUserQuestionProcessor | AskUserQuestion prompts |

## Files Changed

| File | Change |
|------|--------|
| `src/codogram/claude/poller/` | NEW directory |
| `src/codogram/claude/poller/__init__.py` | Package exports |
| `src/codogram/claude/poller/context.py` | PollerContext dataclass |
| `src/codogram/claude/poller/base.py` | BaseProcessor class |
| `src/codogram/claude/poller/crash.py` | Crash detection |
| `src/codogram/claude/poller/poller.py` | Main loop |
| `src/codogram/claude/poller/processors/*.py` | Individual processors |
| `src/codogram/claude/poller.py` | DELETED (moved to poller/) |

## Benefits

1. **Модульность** — каждый processor изолирован, легко тестировать
2. **Расширяемость** — добавить новый processor = создать файл + добавить в список
3. **Читаемость** — маленькие файлы по 20-150 строк вместо одного на 500+
4. **Shared context** — PollerContext передаётся всем processors
5. **Общие helpers** — BaseProcessor содержит send/edit/delete/log методы
