# "Claude ready" отправляется до MCP approval

**Date:** 2026-01-17
**Severity:** Minor (UX confusion)
**Status:** Active

## Summary

При запуске Claude с MCP сервером, сообщение `[v] Claude ready` отправляется ДО того как пользователь одобрит MCP trust prompt. Пользователь видит "ready", но Claude ещё ждёт approval.

## Timeline from logs

```
05:47:20 - tmux_send: claude (отправили команду)
05:47:20 - Thread poller started
05:47:20 - is_claude_ready() → True (видит ────)
05:47:20 - "[v] Claude ready" отправлен
05:47:21 - Poller detected MCP permission prompt
05:47:22 - MCP buttons отправлены в Telegram
```

## Root Cause

`is_claude_ready()` проверяет наличие UI элементов:
1. Две горизонтальные линии `────` (input box borders)
2. `> Try` prompt
3. `? for shortcuts`

Эти элементы рендерятся ДО появления MCP trust modal. Детектор видит input box и считает Claude готовым, хотя поверх него модальное окно MCP approval.

## Impact

- UX confusion: пользователь видит "ready" но Claude не принимает ввод
- Несоответствие статуса реальному состоянию

## Proposed Fix

**Option A: Координация с поллером**
- Не отправлять "ready" пока поллер не подтвердит IDLE состояние
- После `is_claude_ready()=True`, ждать 1-2 цикла поллера без permissions

**Option B: Убрать "Claude ready"**
- Анимация просто заканчивается (рожица исчезает)
- Поллер показывает permissions если есть
- Watcher показывает tool calls когда появятся

**Option C: Проверять numbered options**
- В `is_claude_ready()` добавить негативную проверку
- Если видим "1. " "2. " "3. " — это prompt, не ready
- Менее хрупко чем проверка на "MCP server" текст

## Related

- `2026-01-07-session-not-immediately-active.md` — похожая проблема с timing
