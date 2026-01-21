# AskUserQuestion Support + Poller Refactoring

**Date:** 2026-01-21
**Status:** Design

## Summary

Добавить поддержку AskUserQuestion tool call + рефакторинг permission_poller.py (502 строки → модульная структура).

## Problem

1. **AskUserQuestion не поддерживается** — Claude может задавать вопросы через AskUserQuestion, но бот их игнорирует
2. **permission_poller.py монолитный** — 502 строки, одна god-function, сложно добавлять фичи

## Solution

### 1. Рефакторинг poller

Разбить `permission_poller.py` на модули по ответственностям.

**Файловая структура:**

```
src/codogram/claude/poller/
├── __init__.py          # re-export create_poller_task, create_poller_task_for_thread
├── context.py           # PollerContext dataclass
├── base.py              # BaseProcessor class
├── crash.py             # _detect_crash() function
├── poller.py            # main loop
└── processors/
    ├── __init__.py
    ├── compact.py       # CompactProcessor (~20 строк)
    ├── thinking.py      # ThinkingProcessor (~50 строк)
    ├── suggestions.py   # SuggestionsProcessor (~40 строк)
    ├── stuck.py         # StuckProcessor (~35 строк)
    ├── permissions.py   # PermissionProcessor (~150 строк)
    └── ask_user.py      # AskUserQuestionProcessor (~80 строк) — NEW
```

**PollerContext:**

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
```

**BaseProcessor:**

```python
class BaseProcessor:
    def __init__(self, ctx: PollerContext):
        self.ctx = ctx

    async def process(self, screen: str) -> None:
        raise NotImplementedError

    # Helpers
    async def send(self, text: str, **kwargs) -> list[int]: ...
    async def send_with_key(self, text: str, key: str, **kwargs) -> list[int]: ...
    async def edit_by_key(self, text: str, key: str) -> None: ...
    async def delete_by_key(self, key: str) -> None: ...
```

**Main loop:**

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

        if crash := _detect_crash(screen):
            await notify_crash(ctx, crash)
            return

        for processor in processors:
            await processor.process(screen)
```

### 2. AskUserQuestion детекция (screen.py)

**Новый тип:**

```python
@dataclass
class AskUserQuestion:
    question: str              # "Сколько мониторов?"
    header: str                # "Мониторы"
    options: list[str]         # ["1. 1", "2. 2", "3. 3+", "4. Type something."]
    descriptions: dict[str, str]  # {"1": "Минимализм", "2": "Код + доки", ...}
```

**Детекция:**

Уникальные маркеры AskUserQuestion:
- Два `────` сепаратора (опции между ними)
- `☐` или `☒` в строке навигации (чекбоксы)
- `← ... →` навигация

Permission prompts имеют только один сепаратор.

**Порядок проверок в parse_screen():**

1. MCP trust prompt (box-style `╭╮╯╰│`)
2. **AskUserQuestion** (два `────` + `☐`/`☒`) — NEW
3. Permission prompt (один `────` + `❯` options)
4. Permission without separator (trust folder)
5. Tool progress / Idle

### 3. AskUserQuestion UI в Telegram

**Формат (аналогично permission prompts):**

```
────────────────────
☐ Мониторы

Сколько мониторов?

1. 1 — Минимализм
2. 2 — Код + доки
3. 3+ — Максимум продуктивности
4. Type something.

👆 [1] [2] [3+] [Другое] [✕]
```

**Keyboard:**

```python
def ask_user_keyboard(options: list[str], tmux_session: str) -> InlineKeyboardMarkup:
    # callback_data: ask:{num}:{tmux_session}
    ...
```

**Callback handler:**

- `ask:{num}:{tmux}` → отправить `{num}` в tmux
- `ask:other:{tmux}` → FSM состояние ожидания текста
- `ask:esc:{tmux}` → отправить `Escape`

### 4. "Type something" flow

1. Пользователь кликает "Другое"
2. Бот отправляет номер опции в tmux (навигация)
3. Бот переходит в FSM состояние `waiting_custom_input`
4. Пользователь пишет текст в Telegram
5. Бот отправляет текст + Enter в tmux
6. FSM сбрасывается

### 5. Скрыть AskUserQuestion из watcher

В `history_watcher.py`:

```python
def _entry_to_messages(entry: ParsedEntry, verbose: bool = False) -> list[dict]:
    if entry.content_type == ContentType.TOOL_USE:
        if entry.tool_name == "AskUserQuestion":
            return []  # Скрываем — покажет poller
        ...
```

## Files Changed

| File | Change |
|------|--------|
| `src/codogram/claude/screen.py` | + AskUserQuestion dataclass, + parse logic |
| `src/codogram/claude/poller/` | NEW directory (refactored from permission_poller.py) |
| `src/codogram/claude/poller/processors/ask_user.py` | NEW processor |
| `src/codogram/claude/history_watcher.py` | Hide AskUserQuestion |
| `src/codogram/telegram/keyboards/ask_user.py` | NEW keyboard |
| `src/codogram/handlers/ask_user.py` | NEW callback handler |
| `src/codogram/permission_poller.py` | DELETE (moved to poller/) |

## Testing

E2E через Telegram MCP:
1. Запустить AskUserQuestion в tmux
2. Проверить появление кнопок в Telegram
3. Кликнуть опцию → проверить ответ в tmux
4. Проверить "Type something" flow
5. Проверить multi-question flow (последовательные вопросы)
