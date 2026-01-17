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

**Tags:** critical, settings
**Preconditions:** Project registered, Claude session running

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
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
