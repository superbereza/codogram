# AskUserQuestion Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Добавить поддержку AskUserQuestion tool call — интерактивные вопросы от Claude в Telegram.

**Architecture:** Детекция AskUserQuestion в `screen.py`, новый `AskUserQuestionProcessor`, keyboard и callback handler с поддержкой single-select и multi-select режимов.

**Tech Stack:** Python 3.12, aiogram 3.x, asyncio

**Prerequisite:** Poller refactoring (см. `2026-01-21-poller-refactoring.md`)

---

## Task 1: Add AskUserQuestion detection to screen.py

**Files:**
- Modify: `src/codogram/claude/screen.py`

**Steps:**
1. Add `AskUserQuestion` dataclass with `is_multi_select` field
2. Add `_parse_ask_user_question()` detection function
3. Update `parse_screen()` to check AskUserQuestion after MCP trust
4. Update `ScreenState` type alias

**Commit:** `feat(screen): add AskUserQuestion detection`

---

## Task 2: Create AskUserQuestionProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/ask_user.py`
- Modify: `src/codogram/claude/poller/processors/__init__.py`
- Modify: `src/codogram/claude/poller/poller.py`

**Steps:**
1. Create processor with state machine (IDLE → DEBOUNCING → SHOWING)
2. Track `is_multi_select` for keyboard generation
3. Add to processors list in `poller.py`

**Commit:** `feat(poller): add AskUserQuestionProcessor`

---

## Task 3: Create ask_user_keyboard

**Files:**
- Create: `src/codogram/telegram/keyboards/ask_user.py`
- Modify: `src/codogram/telegram/keyboards/__init__.py`

**Steps:**
1. Create keyboard builder with single/multi-select callback_data formats:
   - Single: `ask:{num}:{tmux}`
   - Multi: `ask:{num}:{total}:{tmux}`
2. Add "Type something" → "Другое" button
3. Add Submit button for multi-select
4. Add Cancel (✕) button

**Commit:** `feat(keyboards): add ask_user_keyboard`

---

## Task 4: Create AskUserQuestion callback handler

> **⚠️ ВАЖНО:**
> 1. **Thread ID нормализация**: Использовать `normalize_thread_id()` при формировании ключей `(chat_id, thread_id)`.
> 2. **Multi-select навигация**: В multi-select цифровые клавиши только toggle, для навигации нужны Down arrows.

**Files:**
- Create: `src/codogram/handlers/ask_user.py`
- Modify: `src/codogram/handlers/__init__.py`
- Modify: `src/codogram/state.py`

**Steps:**
1. Add state dicts: `ask_options_state`, `ask_other_pending`, `active_ask_prompts`
2. Handle callback formats:
   - `ask:{num}:{tmux}` — single-select
   - `ask:{num}:{total}:{tmux}` — multi-select toggle
   - `ask:other:...` — "Type something"
   - `ask:submit:{tmux}` — submit multi-select
   - `ask:esc:{tmux}` — cancel
3. Implement `_handle_other_select()` with single/multi navigation difference

**Commit:** `feat(handlers): add AskUserQuestion callback handler`

---

## Task 5: Handle "Type something" text input

**Files:**
- Modify: `src/codogram/handlers/messages.py`

**Steps:**
1. Add `_handle_ask_other_pending()` function
2. Check `ask_other_pending` before regular message routing
3. Send text via `tmux send-keys -l` (literal mode)
4. Send Enter
5. Clean up state

**Commit:** `feat(messages): handle Type something text input`

---

## Task 6: Hide AskUserQuestion from watcher

**Files:**
- Modify: `src/codogram/claude/history_watcher.py`

**Steps:**
1. In `_entry_to_messages()`, skip `AskUserQuestion` tool_use
2. Return empty list to hide from Telegram

**Commit:** `feat(watcher): hide AskUserQuestion tool_use`

---

## Task 7: Delete active prompt on user message

**Files:**
- Modify: `src/codogram/handlers/messages.py`

**Steps:**
1. Add `_delete_active_ask_prompt()` function
2. Call before routing when user sends a message
3. Clean up all related messages and state

**Commit:** `feat(messages): delete active AskUserQuestion on user input`

---

## Testing

### Single-select
1. Trigger AskUserQuestion with single-select
2. Click option → verify tmux receives number
3. Click "Другое" → type text → verify tmux receives text

### Multi-select
1. Trigger AskUserQuestion with multi-select
2. Toggle options → verify checkboxes update
3. Click Submit → verify tmux receives toggles + Enter
4. Click "Другое" → type text → verify Down arrows + text

### Edge cases
1. Cancel (✕) → verify Escape sent
2. User sends message while prompt active → verify prompt deleted
3. Multiple sequential questions → verify each handled correctly

---

## Post-Implementation Notes

### Bugs Found During Testing

**1. Thread ID Normalization Mismatch**

Симптом: "Type something" не работал — текст не отправлялся в tmux.

Причина: Callback handler сохранял state с `callback.message.message_thread_id`, а message handler искал по `normalize_thread_id()`. В non-forum чатах эти значения отличались.

Фикс:
```python
from .common import normalize_thread_id

thread_id = normalize_thread_id(callback.message.chat, callback.message.message_thread_id)
key = (chat_id, thread_id)
```

**2. Multi-select Navigation Difference**

Симптом: "Type something" работал в single-select, но не в multi-select.

Причина: В multi-select режиме Claude UI нажатие цифровой клавиши не перемещает курсор — только переключает чекбокс.

Фикс:
```python
if is_multi:
    option_num = int(num)
    for _ in range(option_num - 1):
        tmux.send_key("Down")
else:
    tmux.send_key(num)
```

### Key Learnings

1. **Консистентность ключей состояния**: Если используете `(chat_id, thread_id)` как ключ, убедитесь что `thread_id` вычисляется одинаково везде.

2. **Тестирование обоих режимов**: AskUserQuestion может быть single-select или multi-select. Поведение клавиш отличается.

3. **Literal mode для tmux**: Для произвольного текста используйте `tmux send-keys -l` чтобы спецсимволы не интерпретировались.
