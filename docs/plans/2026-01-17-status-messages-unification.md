# Status Messages Unification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Унифицировать все статусные сообщения в `strings.py` для централизованного управления tone-of-voice

**Architecture:** Все пользовательские сообщения как константы в `strings.py`. Handlers и services импортируют `strings` и используют `.format()` для параметризации. Паттерн send vs edit: edit только для callback response (убрать кнопки), send для всех последующих статусов.

**Tech Stack:** Python, aiogram, telegram_queue

---

## Task 1: Add Missing Status Prefixes

**Files:**
- Modify: `src/codogram/strings.py:10-11`

**Step 1: Add STATUS_QUESTION and STATUS_INFO**

```python
# После STATUS_PENDING добавить:
STATUS_QUESTION = "`[?]`"
STATUS_INFO = "`[i]`"
```

**Step 2: Verify**

Run: `grep -n "STATUS_" src/codogram/strings.py | head -10`
Expected: 6 STATUS_* constants

**Step 3: Commit**

```bash
git add src/codogram/strings.py
git commit -m "feat(strings): add STATUS_QUESTION and STATUS_INFO prefixes"
```

---

## Task 2: Add Constants for handlers/worktree_recovery.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/handlers/worktree_recovery.py`

**Step 1: Add constants to strings.py**

В секцию `# --- Worktree Recovery ---` (создать после `# --- Misc ---`):

```python
# --- Worktree Recovery ---

ERR_INVALID_CALLBACK = f"{STATUS_ERR} Invalid callback data"
ERR_PROJECT_NOT_FOUND = f"{STATUS_ERR} Project not found"
ERR_THREAD_NOT_FOUND = f"{STATUS_ERR} Thread not found"

WORKTREE_RECREATE_FAILED = f"""{STATUS_ERR} Failed to recreate worktree: {{path}}

Use /start to create a new session."""

WORKTREE_BRANCH_CREATE_FAILED = f"""{STATUS_ERR} Failed to create branch: {{path}}

Use /start to create a new session."""

WORKTREE_TOPIC_ARCHIVED = f"""{STATUS_OK} Topic archived

The worktree was missing. Topic has been archived."""
```

**Step 2: Replace hardcoded strings in worktree_recovery.py**

Заменить все `callback.message.edit_text(...)` на `telegram_queue.edit(callback.message, strings.CONSTANT)`:

```python
# Было:
await callback.message.edit_text("`[x]` Invalid callback data")

# Стало:
await telegram_queue.edit(callback.message, strings.ERR_INVALID_CALLBACK)
```

Обновить импорты:
```python
from .. import strings
```

**Step 3: Verify**

Run: `grep -c "edit_text" src/codogram/handlers/worktree_recovery.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/handlers/worktree_recovery.py
git commit -m "refactor(worktree_recovery): use strings constants, telegram_queue.edit"
```

---

## Task 3: Add Constants for handlers/finish.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/handlers/finish.py`

**Step 1: Add constants to strings.py**

В секцию `# --- Finish/Archive ---` (создать):

```python
# --- Finish/Archive ---

FINISH_PROJECT_NOT_REGISTERED = f"{STATUS_WARN} Project not registered. Use /start first."
FINISH_THREAD_NOT_FOUND = f"{STATUS_WARN} Thread not found."

FINISH_WORKTREE_NOT_FOUND = f"""{STATUS_WARN} Worktree not found: `{{path}}`

The worktree directory is missing. What to do?"""

FINISH_UNCOMMITTED_CHANGES = f"{STATUS_WARN} Branch `{{branch}}` has uncommitted changes"

FINISH_ARCHIVING = f"{STATUS_PENDING} Archiving `{{name}}`..."
FINISH_ARCHIVED = f"{STATUS_OK} Topic `{{name}}` archived."

FINISH_MERGING = f"{STATUS_PENDING} Merging `{{branch}}` -> `{{target}}`..."
FINISH_MERGE_FAILED = f"""{STATUS_ERR} Merge failed: {{error}}

Fix conflicts and try again."""

FINISH_PUSHING = f"{STATUS_PENDING} Pushing `{{target}}`..."
FINISH_PUSH_FAILED = f"""{STATUS_WARN} Merged but push failed: {{error}}

Push manually: `git push origin {{target}}`"""

FINISH_CLEANING_WORKTREE = f"{STATUS_PENDING} Cleaning up worktree..."
FINISH_ARCHIVING_TOPIC = f"{STATUS_PENDING} Archiving topic..."

FINISH_MERGED_PUSHED = f"{STATUS_OK} Merged and pushed `{{branch}}` -> `{{target}}`"
FINISH_MERGED_LOCAL = f"{STATUS_OK} Merged `{{branch}}` -> `{{target}}` (local only)"
FINISH_WORKTREE_CLEANUP_FAILED = f"\n{STATUS_WARN} Worktree cleanup failed: {{error}}"

FINISH_DISCARDED_ARCHIVED = f"{STATUS_OK} Branch `{{branch}}` discarded and archived."
FINISH_ARCHIVED_WORKTREE_MISSING = f"""{STATUS_OK} Branch `{{branch}}` archived.
Worktree was already missing."""

FINISH_COMMIT_SENT = f"""{STATUS_PENDING} Sent: "Commit current changes in logical chunks with descriptive messages."

Wait for Claude to commit, then try /finish again."""
```

**Step 2: Replace hardcoded strings in finish.py**

Пример замены:
```python
# Было:
await telegram_queue.reply(message, "`[!]` Project not registered. Use /start first.")

# Стало:
await telegram_queue.reply(message, strings.FINISH_PROJECT_NOT_REGISTERED)

# Было:
await telegram_queue.edit(callback.message, f"`[~]` Merging `{branch_name}` -> `{target_branch}`...")

# Стало:
await telegram_queue.edit(callback.message, strings.FINISH_MERGING.format(branch=branch_name, target=target_branch))
```

**Step 3: Verify**

Run: `grep -c '"\`\[' src/codogram/handlers/finish.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/handlers/finish.py
git commit -m "refactor(finish): use strings constants"
```

---

## Task 4: Add Constants for handlers/branches.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/handlers/branches.py`

**Step 1: Add constants to strings.py**

В секцию `# --- Branch Operations ---` (создать):

```python
# --- Branch Operations ---

BRANCH_PROJECT_NOT_REGISTERED = f"{STATUS_WARN} Project not registered. Use /start first."
BRANCH_GIT_REQUIRED = f"{STATUS_ERR} Git repository required for /branch_create"

BRANCH_WORKTREE_NOT_FOUND_BASE = f"""{STATUS_WARN} Worktree not found, using {{default_branch}} as base

Create branch from `{{default_branch}}`?"""

BRANCH_ALREADY_EXISTS = f"{STATUS_ERR} Branch `{{name}}` already exists"
BRANCH_DIR_EXISTS = f"{STATUS_ERR} Directory already exists: `{{path}}`"
BRANCH_UNCOMMITTED_CHANGES = f"{STATUS_WARN} Uncommitted changes detected"
BRANCH_UNCOMMITTED_IN_BASE = f"{STATUS_WARN} Uncommitted changes in {{base_branch}}"

BRANCH_COMMIT_SENT = f"""{STATUS_PENDING} Sent: "Commit current changes in logical chunks with descriptive messages."

Wait for Claude to commit, then try /branch again."""
```

**Step 2: Replace hardcoded strings in branches.py**

**Step 3: Verify**

Run: `grep -c '"\`\[' src/codogram/handlers/branches.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/handlers/branches.py
git commit -m "refactor(branches): use strings constants"
```

---

## Task 5: Add Constants for handlers/sessions.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/handlers/sessions.py`

**Step 1: Add/Update constants in strings.py**

Некоторые уже есть (SESSION_*, NEW_SESSION, CLEAR_SESSION, RESUME_*). Проверить и добавить недостающие:

```python
# В секции # --- Session management ---
SESSION_CLAUDE_READY = f"{STATUS_OK} Claude ready"
```

**Step 2: Replace hardcoded strings in sessions.py**

```python
# Было:
f"`[v]` Claude ready"

# Стало:
strings.SESSION_CLAUDE_READY
```

**Step 3: Verify**

Run: `grep -c '"\`\[' src/codogram/handlers/sessions.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/handlers/sessions.py
git commit -m "refactor(sessions): use strings constants"
```

---

## Task 6: Add Constants for handlers/start.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/handlers/start.py`

**Step 1: Add constants to strings.py**

В секцию `# --- Start Flow ---` (создать):

```python
# --- Start Flow ---

START_THREAD_RUNNING = f"""{STATUS_OK} Thread `{{thread_name}}` running

Attach: `tmux attach -t {{tmux_session}}`"""

START_ALREADY_RUNNING = f"""{STATUS_OK} Already running

Attach: `tmux attach -t {{tmux_name}}`"""

START_SESSION_NOT_FOUND = f"{STATUS_WARN} Previous session not found"

START_WORKTREE_NOT_FOUND = f"{STATUS_WARN} Worktree not found: `{{path}}`"

START_WORKTREE_NOT_FOUND_OPTIONS = f"""{STATUS_WARN} Worktree not found: `{{path}}`

What to do?"""

START_NEW_SESSION = f"{STATUS_PENDING} Starting new session..."
START_RECREATING_WORKTREE = f"{STATUS_PENDING} Recreating worktree..."
START_WORKTREE_RECREATED = f"{STATUS_OK} Worktree recreated. Use /start to launch."
START_WORKTREE_RECREATE_FAILED = f"{STATUS_ERR} Failed to recreate: {{error}}"
```

**Step 2: Replace hardcoded strings in start.py**

**Step 3: Verify**

Run: `grep -c '"\`\[' src/codogram/handlers/start.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/handlers/start.py
git commit -m "refactor(start): use strings constants"
```

---

## Task 7: Add Constants for handlers/common.py and create_flow.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/handlers/common.py`
- Modify: `src/codogram/handlers/create_flow.py`

**Step 1: Add constants to strings.py**

В секцию `# --- Misc ---`:

```python
TOPICS_REQUIRED_GROUP = f"{STATUS_WARN} This command requires a group with topics."
TOPICS_REQUIRED_ENABLE = f"{STATUS_WARN} Topics required. Enable in group settings -> Topics"

CREATE_PROJECT_NOT_FOUND = f"{STATUS_WARN} Project not found"
CREATE_TOPIC_ERROR = f"{STATUS_ERR} Error creating topic"
```

**Step 2: Replace hardcoded strings**

**Step 3: Verify**

Run: `grep -c '"\`\[' src/codogram/handlers/common.py src/codogram/handlers/create_flow.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/handlers/common.py src/codogram/handlers/create_flow.py
git commit -m "refactor(common,create_flow): use strings constants"
```

---

## Task 8: Add Constants for services/create_flow.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/services/create_flow.py`

**Step 1: Add constants to strings.py**

В секцию `# --- Validation ---` (создать):

```python
# --- Validation ---

VALIDATE_INVALID_NAME = f"{STATUS_ERR} Invalid name"
VALIDATE_NAME_TOO_LONG = f"{STATUS_ERR} Name too long (max {{max_len}} chars)"
VALIDATE_NAME_EXISTS = f"{STATUS_ERR} Name `{{name}}` already used"
VALIDATE_GIT_REQUIRED = f"{STATUS_ERR} Git repository required"
VALIDATE_UNCOMMITTED = f"{STATUS_WARN} Uncommitted changes"
```

**Step 2: Replace hardcoded strings**

**Step 3: Verify**

Run: `grep -c '"\`\[' src/codogram/services/create_flow.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/services/create_flow.py
git commit -m "refactor(services/create_flow): use strings constants"
```

---

## Task 9: Add Constants for services/launch.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/services/launch.py`

**Step 1: Add constants to strings.py**

В секцию `# --- Launch ---` (переименовать из `# --- Launch animation ---`):

```python
# --- Launch ---

LAUNCH_CREATING_BRANCH = f"{STATUS_PENDING} Creating branch `{{branch}}` from `{{base}}`..."
LAUNCH_BRANCH_ERROR = f"{STATUS_ERR} {{error}}"
LAUNCH_WORKTREE_CREATED = f"{STATUS_OK} Worktree: `{{path}}`"
```

**Step 2: Replace hardcoded strings**

**Step 3: Verify**

Run: `grep -c '"\`\[' src/codogram/services/launch.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/services/launch.py
git commit -m "refactor(services/launch): use strings constants"
```

---

## Task 10: Add Constants for history_watcher.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/history_watcher.py`

**Step 1: Verify existing constants**

`SESSION_CLOSED`, `SESSION_BOUND`, `SESSION_NOT_FOUND` уже есть в strings.py.

**Step 2: Replace hardcoded strings**

```python
# Было:
{"text": f"`[!]` Claude session closed: {thread.name}", ...}

# Стало:
{"text": strings.SESSION_CLOSED.format(name=thread.name), ...}
```

**Step 3: Verify**

Run: `grep -c '"\`\[' src/codogram/history_watcher.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "refactor(history_watcher): use strings constants"
```

---

## Task 11: Add Constants for permission_poller.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/permission_poller.py`

**Step 1: Add constants to strings.py**

В секцию `# --- Session management ---`:

```python
CLAUDE_CRASHED = f"{STATUS_WARN} Claude crashed: {{reason}}\nUse /restart to restart."
```

**Step 2: Replace hardcoded strings**

**Step 3: Verify**

Run: `grep -c '"\`\[' src/codogram/permission_poller.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/permission_poller.py
git commit -m "refactor(permission_poller): use strings constants"
```

---

## Task 12: Add Constants for middleware/admin.py

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/middleware/admin.py`

**Step 1: Add constants to strings.py**

В секцию `# --- Errors ---` (создать):

```python
# --- Errors ---

ERR_NOT_ADMIN = f"""{STATUS_ERR} Not admin. Your ID: `{{user_id}}`
Add your ID to ADMIN_IDS in .env"""
```

**Step 2: Replace hardcoded strings**

**Step 3: Verify**

Run: `grep -c '"\`\[' src/codogram/middleware/admin.py`
Expected: 0

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/middleware/admin.py
git commit -m "refactor(middleware/admin): use strings constants"
```

---

## Task 13: Update launch_animation.py (verify existing constants)

**Files:**
- Modify: `src/codogram/launch_animation.py`

**Step 1: Check which constants already exist**

`LAUNCH_*` constants already in strings.py. Verify usage matches.

**Step 2: Replace any remaining hardcoded strings**

```python
# Было:
await queue.send(chat_id, "`[~]` Resuming session...", ...)

# Если нужно добавить:
LAUNCH_RESUMING = f"{STATUS_PENDING} Resuming session..."
```

**Step 3: Add missing constants if needed**

В секцию `# --- Launch ---`:

```python
LAUNCH_RESUMING = f"{STATUS_PENDING} Resuming session..."
LAUNCH_PROJECT_CWD_NOT_SET = f"{STATUS_ERR} Project cwd not set. Re-register with /start"
```

**Step 4: Verify**

Run: `grep -c '"\`\[' src/codogram/launch_animation.py`
Expected: 0

**Step 5: Commit**

```bash
git add src/codogram/strings.py src/codogram/launch_animation.py
git commit -m "refactor(launch_animation): use strings constants"
```

---

## Task 14: Apply send vs edit Pattern in finish.py

**Files:**
- Modify: `src/codogram/handlers/finish.py`

**Step 1: Review merge flow**

Текущий flow в `on_merge_confirm`:
1. `edit` - убрать кнопки, показать "Merging..."
2. `edit` - "Pushing..."
3. `edit` - "Archiving topic..."
4. `edit` - "Cleaning up worktree..."
5. `edit` - финальный статус

**Step 2: Refactor to send pattern**

```python
async def on_merge_confirm(callback, ...):
    # 1. Убираем кнопки (edit)
    await telegram_queue.edit(callback.message, strings.FINISH_MERGING.format(...))
    await callback.answer()

    # 2. Последующие шаги (send)
    result = merge_branch(...)
    if not result.success:
        await telegram_queue.send(chat_id, strings.FINISH_MERGE_FAILED.format(...), thread_id=thread_id)
        return

    await telegram_queue.send(chat_id, strings.FINISH_PUSHING.format(...), thread_id=thread_id)
    # ... и т.д.

    # 3. Финальный статус (send)
    await telegram_queue.send(chat_id, strings.FINISH_MERGED_PUSHED.format(...), thread_id=thread_id)
```

**Step 3: Verify**

Run: `./dev-run.sh` и протестировать /finish flow вручную

**Step 4: Commit**

```bash
git add src/codogram/handlers/finish.py
git commit -m "refactor(finish): apply send vs edit pattern for status chains"
```

---

## Task 15: Branch Creation UX - Remove Menu, Send Confirmation

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/handlers/branches.py` (or relevant handler)

**Step 1: Add constants to strings.py**

```python
# В секции # --- Branch Operations ---
BRANCH_CREATING = f"{STATUS_PENDING} Creating branch `{{name}}`..."
BRANCH_CREATED = f"{STATUS_OK} Branch `{{name}}` created"
```

**Step 2: Update branch creation handler**

При подтверждении создания бранча:
```python
# 1. Убираем кнопки (edit)
await telegram_queue.edit(callback.message, strings.BRANCH_CREATING.format(name=branch_name))
await callback.answer()

# 2. Создаём бранч...
result = create_branch(...)

# 3. Финальный статус (send)
await telegram_queue.send(chat_id, strings.BRANCH_CREATED.format(name=branch_name), thread_id=thread_id)
```

**Step 3: Verify**

Протестировать /branch flow — меню должно исчезнуть, появиться сообщение о создании.

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/handlers/branches.py
git commit -m "feat(branches): remove menu on confirm, send creation status"
```

---

## Task 16: Thread Creation UX - Remove Menu, Send Confirmation

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/handlers/threads.py` (or relevant handler)

**Step 1: Add constants to strings.py**

```python
# В секции # --- Project/Thread ---
THREAD_CREATING = f"{STATUS_PENDING} Creating thread `{{name}}`..."
THREAD_CREATED = f"{STATUS_OK} Thread `{{name}}` created"
```

**Step 2: Update thread creation handler**

При подтверждении создания треда:
```python
# 1. Убираем кнопки (edit)
await telegram_queue.edit(callback.message, strings.THREAD_CREATING.format(name=thread_name))
await callback.answer()

# 2. Создаём тред...
result = create_thread(...)

# 3. Финальный статус (send)
await telegram_queue.send(chat_id, strings.THREAD_CREATED.format(name=thread_name), thread_id=thread_id)
```

**Step 3: Verify**

Протестировать /thread flow — меню должно исчезнуть, появиться сообщение о создании.

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/handlers/threads.py
git commit -m "feat(threads): remove menu on confirm, send creation status"
```

---

## Task 17: Final Verification

**Step 1: Check no hardcoded status prefixes remain**

```bash
grep -r '"\`\[v\]\`\|"\`\[x\]\`\|"\`\[!\]\`\|"\`\[~\]\`' src/codogram/ --include="*.py" | grep -v strings.py
```

Expected: No results (or only in strings.py)

**Step 2: Run bot and test key flows**

- /start flow
- /finish flow (merge, archive)
- /branch flow
- Error cases (missing worktree, etc.)

**Step 3: Verify E2E tests still pass**

Если есть E2E тесты — запустить и проверить.

**Step 4: Final commit (if needed)**

```bash
git add -A
git commit -m "chore: final cleanup after strings unification"
```

---

## Summary

| Task | Files | Description |
|------|-------|-------------|
| 1 | strings.py | Add STATUS_QUESTION, STATUS_INFO |
| 2 | strings.py, worktree_recovery.py | Extract constants, fix .edit_text() |
| 3 | strings.py, finish.py | Extract ~15 constants |
| 4 | strings.py, branches.py | Extract ~8 constants |
| 5 | strings.py, sessions.py | Extract ~5 constants |
| 6 | strings.py, start.py | Extract ~10 constants |
| 7 | strings.py, common.py, create_flow.py | Extract ~4 constants |
| 8 | strings.py, services/create_flow.py | Extract ~5 constants |
| 9 | strings.py, services/launch.py | Extract ~3 constants |
| 10 | history_watcher.py | Use existing constants |
| 11 | strings.py, permission_poller.py | Extract ~1 constant |
| 12 | strings.py, middleware/admin.py | Extract ~1 constant |
| 13 | strings.py, launch_animation.py | Verify/fix existing constants |
| 14 | finish.py | Apply send vs edit pattern |
| 15 | strings.py, branches.py | Branch creation UX - remove menu, send confirmation |
| 16 | strings.py, threads.py | Thread creation UX - remove menu, send confirmation |
| 17 | All | Final verification |

**Total:** ~70-75 new constants in strings.py, ~12 files refactored
