# Setup Flow Bugfixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three bugs in setup flow and rename misleading enum value.

**Architecture:** In-memory guards for race conditions, consistent message tracking, prompt-aware launch loop.

**Tech Stack:** Python, aiogram 3.x, asyncio

---

## Summary of Issues

1. **Duplicate "How would you like to set up this project?"** — Telegram sends two events on bot add, both handlers race
2. **"Cloning repo..." deleted immediately** — `bot_message_id` only tracked in new_project_flow, not clone/connect
3. **Timeout on trust prompt** — `is_claude_ready()` doesn't see prompts, launch loop times out
4. **Misleading enum name** — `PromptType.MCP_TRUST` → `TRUST_PROMPT` (folder trust is not MCP)

---

### Task 1: Fix duplicate setup message with in-memory guard

**Files:**
- Modify: `src/codogram/handlers/setup/triggers.py`

**Step 1: Add module-level guard set and filter**

At the top of triggers.py (after imports, around line 23):

```python
# In-memory guard against concurrent setup flows
# Python GIL makes set operations atomic
_setup_in_progress: set[int] = set()


class SetupNotInProgress(BaseFilter):
    """Filter that passes only if chat is NOT currently starting setup."""

    async def __call__(self, message: Message) -> bool:
        return message.chat.id not in _setup_in_progress
```

**Step 2: Add guard to `on_bot_added`**

In `on_bot_added` function, after the `old_status` check (around line 76), add:

```python
    # Guard against race with on_any_message
    if chat.id in _setup_in_progress:
        logger.debug(f"Setup already starting for chat {chat.id}")
        return
```

**Step 3: Add filter to `on_any_message`**

Update the decorator (around line 134):

```python
@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    ProjectNotRegistered(),
    NotInSetupFlow(),
    SetupNotInProgress(),  # NEW: prevent race with on_bot_added
)
async def on_any_message(message: Message, state: FSMContext):
```

**Step 4: Wrap `_start_setup_flow` with guard**

Modify `_start_setup_flow` (around line 153):

```python
async def _start_setup_flow(bot: Bot, chat: Chat, state: FSMContext):
    """Start the setup flow - check base_dir first, then admin rights."""
    # Guard against concurrent calls
    if chat.id in _setup_in_progress:
        logger.debug(f"Setup already in progress for chat {chat.id}")
        return

    _setup_in_progress.add(chat.id)
    try:
        # ... ALL existing logic stays the same ...
        # (base_dir check, menu registration, admin rights check, send message)
    finally:
        _setup_in_progress.discard(chat.id)
```

**Step 5: Test manually**

1. Remove bot from test group
2. Add bot back to group
3. Verify only ONE "How would you like to set up this project?" message appears
4. Check logs for "Setup already starting" or "Setup already in progress" debug messages

**Step 6: Commit**

```bash
git add src/codogram/handlers/setup/triggers.py
git commit -m "fix: prevent duplicate setup message with in-memory guard"
```

---

### Task 2: Fix progress message deletion with consistent tracking

**Files:**
- Modify: `src/codogram/handlers/setup/clone_flow.py`
- Modify: `src/codogram/handlers/setup/connect_flow.py`
- Modify: `src/codogram/handlers/setup/launch.py`

**Step 1: Track progress message in clone_flow**

In `_do_clone` (clone_flow.py, around line 149), after sending progress message:

```python
async def _do_clone(message: Message, state: FSMContext):
    """Perform the git clone operation."""
    data = await state.get_data()
    url = data["clone_url"]
    target_dir = data["target_dir"]
    project_name = data["project_name"]

    # Show progress and track message ID
    progress_msg = await message.answer(strings.SETUP_CLONE_PROGRESS, parse_mode="MarkdownV2")
    await state.update_data(bot_message_id=progress_msg.message_id)  # NEW: track for cleanup

    # ... rest of function unchanged ...
```

**Step 2: Track folder selection message in connect_flow**

In `show_folder_selection` (connect_flow.py), track the message. Find the function and update:

```python
async def show_folder_selection(message: Message, state: FSMContext, page: int = 0):
    """Show folder selection with pagination."""
    # ... existing logic to build folders list and keyboard ...

    # Edit or send message
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode="MarkdownV2")
        await state.update_data(bot_message_id=message.message_id)  # NEW: track
    except Exception:
        sent = await message.answer(text, reply_markup=kb, parse_mode="MarkdownV2")
        await state.update_data(bot_message_id=sent.message_id)  # NEW: track
```

**Step 3: Fix deletion logic in launch.py**

In `_execute_launch` (launch.py, lines 129-140), make deletion more intentional:

```python
async def _execute_launch(message: Message, state: FSMContext):
    """Execute the actual launch (after rename decision)."""
    # ... imports ...

    # Enter launching state (blocks user input)
    await state.set_state(SetupFlow.launching)

    data = await state.get_data()

    # Delete tracked bot message (progress, folder selection, git choice, etc.)
    if prev_msg_id := data.get("bot_message_id"):
        try:
            await message.bot.delete_message(message.chat.id, prev_msg_id)
        except Exception:
            pass

    # Note: We do NOT delete the current message unconditionally anymore.
    # The tracked bot_message_id handles cleanup for all flows.
    # If message is from rename callback, it's already the same as bot_message_id
    # (since rename uses edit_text on the tracked message).

    # ... rest of function unchanged ...
```

**Step 4: Remove unconditional message.delete()**

Remove lines 136-140 that unconditionally delete the message:

```python
    # REMOVE THIS BLOCK:
    # try:
    #     await message.delete()
    # except Exception:
    #     pass
```

**Step 5: Test all three flows**

1. **Clone flow:** Enter URL → verify "Cloning..." stays visible during clone → deleted on launch
2. **Connect flow:** Select folder → verify folder list deleted on launch
3. **New project flow:** Enter name → git choice → verify git choice deleted on launch

**Step 6: Commit**

```bash
git add src/codogram/handlers/setup/clone_flow.py src/codogram/handlers/setup/connect_flow.py src/codogram/handlers/setup/launch.py
git commit -m "fix: consistent message tracking across all setup flows"
```

---

### Task 3: Fix timeout during trust prompt

**Files:**
- Modify: `src/codogram/launch_animation.py`

**Step 1: Import parse_screen and PermissionPrompt**

At the top of launch_animation.py, add import:

```python
from .screen import is_claude_ready, parse_screen, PermissionPrompt
```

**Step 2: Add prompt detection to ready check loop**

In `launch_with_animation`, modify the while loop (around line 125):

```python
        while True:
            # Check if Claude UI is fully loaded
            if tmux.is_claude_ready():
                break

            # Also check if a prompt is showing (Claude is running, waiting for user)
            pane_content = tmux.capture_pane()
            parsed = parse_screen(pane_content)
            if isinstance(parsed, PermissionPrompt):
                logger.info(f"launch_ready_via_prompt: type={parsed.prompt_type.value}")
                break

            elapsed = time.time() - start_time

            # Debug: log what we see in tmux every 10 seconds
            if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                logger.debug(f"launch_wait: elapsed={elapsed:.0f}s, pane_preview={pane_content[-200:] if pane_content else 'empty'}")

            # Timeout check
            if elapsed > settings.claude_launch_timeout:
                if face_msg_id:
                    try:
                        await bot.delete_message(chat_id, face_msg_id)
                    except Exception:
                        pass
                await queue.send(
                    chat_id, strings.LAUNCH_TIMEOUT,
                    thread_id=thread_id,
                    parse_mode="MarkdownV2"
                )
                return False

            # Face animation
            # ... existing animation code unchanged ...

            await asyncio.sleep(3)
```

**Step 3: Test with trust prompt**

1. Use fresh workspace or configure new MCP server
2. Run `/start` in test group
3. When trust prompt appears, verify NO timeout occurs
4. Check logs for "launch_ready_via_prompt" message
5. Accept the prompt
6. Verify Claude continues normally

**Step 4: Commit**

```bash
git add src/codogram/launch_animation.py
git commit -m "fix: detect prompts as ready state during launch"
```

---

### Task 4: Rename MCP_TRUST to TRUST_PROMPT

**Files:**
- Modify: `src/codogram/screen.py` (5 locations)
- Modify: `tests/test_screen.py` (3 locations)
- Modify: `tests/test_auto_accept.py` (2 locations)

**Step 1: Rename enum in screen.py**

Line 34:
```python
class PromptType(Enum):
    REGULAR = "regular"
    TRUST_PROMPT = "trust_prompt"  # Renamed from MCP_TRUST
```

**Step 2: Update docstring in screen.py**

Line 107 (in `_parse_mcp_trust_prompt` docstring):
```python
    """Parse box-style trust prompt (MCP server or folder trust).

    Returns PermissionPrompt with TRUST_PROMPT type, or None if not trust prompt.
    """
```

**Step 3: Update all enum references in screen.py**

Line 150:
```python
        prompt_type=PromptType.TRUST_PROMPT
```

Line 209:
```python
        return PermissionPrompt(options=options, body=body, prompt_type=PromptType.TRUST_PROMPT)
```

Line 229:
```python
        return PermissionPrompt(options=options, body=body, prompt_type=PromptType.TRUST_PROMPT)
```

**Step 4: Update test_screen.py**

Line 124:
```python
    assert result.prompt_type == PromptType.TRUST_PROMPT
```

Line 201:
```python
    assert result.prompt_type == PromptType.TRUST_PROMPT
```

Line 226:
```python
    assert result.prompt_type == PromptType.TRUST_PROMPT
```

**Step 5: Update test_auto_accept.py**

Line 89:
```python
    assert PromptType.TRUST_PROMPT not in AUTO_ACCEPT_TYPES
```

Line 106:
```python
    prompt_type=PromptType.TRUST_PROMPT,
```

**Step 6: Run tests**

```bash
pytest tests/test_screen.py tests/test_auto_accept.py -v
```

Expected: All tests pass

**Step 7: Commit**

```bash
git add src/codogram/screen.py tests/test_screen.py tests/test_auto_accept.py
git commit -m "refactor: rename MCP_TRUST to TRUST_PROMPT for clarity"
```

---

## Testing Checklist

- [ ] Bot add to group → single setup message (no duplicate)
- [ ] Clone flow → "Cloning..." stays visible, deleted on launch
- [ ] Connect flow → folder list deleted on launch
- [ ] New project flow → git choice deleted on launch
- [ ] Trust prompt during launch → no timeout, continues after accept
- [ ] All existing tests pass
- [ ] Permission prompts still work correctly
