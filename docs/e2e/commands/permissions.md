# Permission Poller Tests

Permission button delivery and handling.

## TC-PERMISSIONS-001: Permission buttons in correct topic

**Tags:** smoke, critical, permissions
**Preconditions:** Active session in topic, Claude asking for permission

**Setup:**
```bash
# Ensure session in topic
cat .config.json | jq '.projects["codogram-testing-area"].threads["303"]'
```

**Steps:**
```python
# Ask Claude to do something requiring permission (e.g., run bash)
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="Run: echo hello")
# Wait 15s for permission prompt
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: Inline buttons (Yes/No or tool options) appear in topic 303
- State: Poller task running for this thread

---

## TC-PERMISSIONS-002: Permission buttons NOT in other topics (isolation)

**Tags:** critical, permissions, isolation
**Preconditions:** Two active topics

**Setup:**
```bash
# Two topics with sessions
# Topic A: 303
# Topic B: 222
```

**Steps:**
```python
# Trigger permission in Topic A
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="Run: ls /tmp")
# Wait 15s
# Check Topic B for buttons - should be empty
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=222, limit=3)
# Check Topic A for buttons - should have them
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: Permission buttons ONLY in Topic A
- State: Pollers are thread-isolated

---

## TC-PERMISSIONS-003: Button click works

**Tags:** critical, permissions
**Preconditions:** Permission prompt visible

**Steps:**
```python
# Find and click Yes button
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Yes")
# Wait 10s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: Button click acknowledged, tool executes
- State: Permission sent to Claude, execution continues

---

## TC-PERMISSIONS-004: auto_accept works

**Tags:** critical, permissions
**Preconditions:** auto_accept enabled for thread

**Setup:**
```python
# Enable auto_accept
mcp__telegram__send_message(chat_id=-1003356094635, message="/auto_accept")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Steps:**
```python
# Trigger permission
mcp__telegram__send_message(chat_id=-1003356094635, message="Run: echo auto test")
# Wait 15s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: No permission buttons, tool executes automatically
- State: auto_accept=true in config, permission auto-clicked

**Cleanup:**
```python
# Disable auto_accept
mcp__telegram__send_message(chat_id=-1003356094635, message="/auto_accept")
```
