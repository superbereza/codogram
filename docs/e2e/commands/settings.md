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

## TC-SETTINGS-002: /settings shows project info

**Tags:** full, settings
**Preconditions:** Project registered

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Project name, cwd, auto_accept status
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
