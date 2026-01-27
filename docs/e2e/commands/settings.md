# /help, /settings, /auto_accept Tests

Settings and configuration commands.

## TC-SETTINGS-001: /help responds

**Tags:** smoke, settings
**Preconditions:** None

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/help")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Help message with list of commands
- State: None

---

## TC-SETTINGS-002: /settings shows project info and Claude session state

> **Note:** This test describes the OLD format. See TC-SETTINGS-008 for NEW format with circle indicators and inline buttons.

**Tags:** critical, settings, deprecated
**Preconditions:** Project registered, Claude session running

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected (OLD format - superseded by TC-SETTINGS-008):**
- UI: Response contains:
  - Settings header with project/thread name
  - Auto-accept status (⚡ ON or OFF)
  - Approval mode (one of: "default mode on", "⏵⏵ accept edits on", "⏸ plan mode on")
  - /shift_tab hint
  - Background tasks count ("no background tasks" or "N background tasks")
  - Context percent ("context left until autocompact: N%")
- State: None

---

## TC-SETTINGS-003: /auto_accept toggles

**Tags:** full, settings
**Preconditions:** None

**Setup:**
```bash
# Get current state
cat .config.json | jq '.projects["codogram-testing-area"].threads["null"].auto_accept'
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/auto_accept")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: "Auto-accept enabled/disabled"
- State: auto_accept toggled in config

---

## TC-SETTINGS-004: /get_debug_ids shows IDs

**Tags:** full, settings
**Preconditions:** None

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/get_debug_ids")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: user_id, chat_id, thread_id values
- State: None

---

## TC-SETTINGS-005: /shift_tab cycles approval mode

**Tags:** critical, settings, shift_tab
**Preconditions:** Project registered, Claude session running in default mode

**Steps:**
```python
# Send shift_tab command
mcp__telegram__send_message(chat_id=-1003356094635, message="/shift_tab")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Response shows new mode (one of: "⏵⏵ accept edits on", "⏸ plan mode on", "default mode on")
- State: Claude approval mode changes in tmux

---

## TC-SETTINGS-006: /shift_tab cycles through all modes

**Tags:** full, settings, shift_tab
**Preconditions:** Project registered, Claude session running

**Steps:**
```python
# First cycle
mcp__telegram__send_message(chat_id=-1003356094635, message="/shift_tab")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)

# Second cycle
mcp__telegram__send_message(chat_id=-1003356094635, message="/shift_tab")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)

# Third cycle
mcp__telegram__send_message(chat_id=-1003356094635, message="/shift_tab")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Three different modes cycled in order:
  - default mode → accept edits → plan mode → default mode
- State: Modes match /settings output

---

## TC-SETTINGS-007: /shift_tab without project

**Tags:** full, settings, shift_tab
**Preconditions:** Chat without registered project

**Steps:**
```python
# Send to unregistered chat/topic
mcp__telegram__send_message(chat_id=UNREGISTERED_CHAT, message="/shift_tab")
# Wait 2s
mcp__telegram__list_messages(chat_id=UNREGISTERED_CHAT, limit=2)
```

**Expected:**
- UI: "No project. Use /start first."
- State: None

---

## TC-SETTINGS-008: /settings shows new format with inline buttons

**Tags:** critical, settings, verbose
**Preconditions:** Project registered

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: Response contains:
  - Project/thread name as header
  - "chat" section with:
    - `• auto-accept: ○ off` or `• auto-accept: ● on`
    - `• verbose: ○ off` or `• verbose: ● on`
  - "claude" section with:
    - `• mode: default` (or "accept edits", "plan mode")
    - `• background tasks: N`
    - `• context: N%`
- Buttons: Three inline buttons vertically:
  - `/auto_accept`
  - `/verbose`
  - `/shift_tab`
- State: None

---

## TC-SETTINGS-009: /verbose toggles verbose mode

**Tags:** critical, settings, verbose
**Preconditions:** Project registered

**Setup:**
```bash
# Get current state
cat ~/.codogram/config.json | jq '.projects["codogram-testing-area"].threads["null"].verbose'
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/verbose")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: `Verbose output: ● on` or `Verbose output: ○ off`
- State: verbose toggled in config

---

## TC-SETTINGS-010: /auto_accept uses circle indicators

**Tags:** full, settings, verbose
**Preconditions:** Project registered

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/auto_accept")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: `Auto-accept: ● on` or `Auto-accept: ○ off` (with circle indicators)
- State: auto_accept toggled in config

---

## TC-SETTINGS-011: Settings inline button toggles auto_accept

**Tags:** full, settings, verbose
**Preconditions:** Project registered, /settings message visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="/auto_accept")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Settings message updated with toggled auto-accept status
- Callback answer: `Auto-accept: ● on` or `Auto-accept: ○ off`
- State: auto_accept toggled in config

---

## TC-SETTINGS-012: Settings inline button toggles verbose

**Tags:** full, settings, verbose
**Preconditions:** Project registered, /settings message visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="/verbose")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Settings message updated with toggled verbose status
- Callback answer: `Verbose: ● on` or `Verbose: ○ off`
- State: verbose toggled in config

---

## TC-SETTINGS-013: Settings inline button cycles mode

**Tags:** full, settings, verbose
**Preconditions:** Project registered, Claude session running, /settings message visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="/shift_tab")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Settings message updated with new mode
- Callback answer: `Mode: accept edits` or `Mode: plan mode` or `Mode: default`
- State: Claude approval mode changed

---

# Less Noise Features (2026-01)

## TC-NOISE-001: Verbose Mode Menu

**Tags:** critical, settings, verbose_mode
**Preconditions:** Project registered, Claude running

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/verbose_mode")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: Message shows "**Verbose mode**" with current setting and description
- Buttons: [show all], [-5] [lines: N] [+5], [headers only], [only current], [total silence], [close]
- State: None

---

## TC-NOISE-002: Change Display Mode via Menu

**Tags:** full, settings, verbose_mode
**Preconditions:** /verbose_mode menu open

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="headers only")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Button becomes [headers only] (selected)
- UI: Mode description updates to "Show tool headers only, no body"
- Callback answer: "Mode: headers"
- State: display_mode = "headers" in config

---

## TC-NOISE-003: Adjust Line Limit

**Tags:** full, settings, verbose_mode
**Preconditions:** /verbose_mode menu open, lines mode selected

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="+5")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Line count increases by 5 (e.g., "lines: 10")
- Callback answer: "Lines: 10"
- State: line_limit updated in config

---

## TC-NOISE-004: Bullet Toggle Command

**Tags:** critical, settings, display_bullet
**Preconditions:** Project registered

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/display_bullet")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Response shows "Bullet prefix: ○ off" or "Bullet prefix: ● on"
- State: display_bullet toggled in config

---

## TC-NOISE-005: Thinking Text Toggle Command

**Tags:** critical, settings, display_thinking_text
**Preconditions:** Project registered

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/display_thinking_text")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Response shows "Show thinking blocks: ○ off" or "Show thinking blocks: ● on"
- State: display_thinking_text toggled in config

---

## TC-NOISE-006: Working Status Toggle

**Tags:** full, settings, working_status
**Preconditions:** Project registered

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/working_status")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Response shows "Working status indicator: ○ off" or "Working status indicator: ● on"
- State: working_status toggled in config

---

## TC-NOISE-007: Settings Shows New UI Section

**Tags:** critical, settings
**Preconditions:** Project registered

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Response contains sections in order:
  - "chat" with /auto_accept, /response_mode
  - "claude" with mode, background tasks, context
  - "ui" with /verbose_mode, /display_bullet, /display_thinking_text
  - "experimental features" with /working_status, /exp_suggestions, /exp_avatar_pack
- State: None

---

## TC-NOISE-008: Settings Pagination

**Tags:** full, settings, pagination
**Preconditions:** Project registered, /settings message visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 2s
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
# Press next page
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text=">")
# Wait 2s
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- Initial buttons: /auto_accept, /response_mode, [>]
- After ">": /verbose_mode, /display_bullet, /display_thinking_text, [<], [>]
- State: None (pagination is UI only)

---

## TC-NOISE-009: Collapsible Permission Prompt (ASK USER)

**Tags:** critical, permissions, collapsible
**Preconditions:** Project registered, auto_accept OFF, Claude running

**Steps:**
```python
# Trigger a permission prompt by asking Claude to write a file
mcp__telegram__send_message(chat_id=-1003356094635, message="Create a file /tmp/test.txt with content 'hello'")
# Wait for Claude to request permission
```

**ASK USER:** "Do you see a permission prompt with [Show more] button and numbered option buttons [1] [2] [3]?"

**Expected:**
- UI: Single message with header + options (collapsed)
- UI: [Show more] button visible
- UI: Option buttons [1] [2] [3] [Cancel]
- State: permission_states contains entry

---

## TC-NOISE-010: Expand Permission Prompt (ASK USER)

**Tags:** full, permissions, collapsible
**Preconditions:** Collapsed permission prompt visible

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Show more")
# Wait 2s
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**ASK USER:** "Do you see the expanded body with separator lines and [Show less] button?"

**Expected:**
- UI: Body content now visible with ──────── separators
- UI: [Show less] button replaces [Show more]
- UI: If long content: [◀] [▶] pagination buttons appear
- State: permission_states.expanded = True
