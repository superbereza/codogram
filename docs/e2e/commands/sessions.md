# /clear_context, /esc, /reset_chat Tests

Session management commands.

## TC-SESSIONS-001: /clear_context creates new session

**Tags:** critical, sessions
**Preconditions:** Active session exists

Aliases: `/clear`, `/new`

**Setup:**
```bash
# Ensure active session
cat .config.json | jq '.projects["codogram-testing-area"].threads["null"].session_id'
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/clear_context")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=3)
```

**Expected:**
- UI: "[~] Clearing Claude context..."
- State: `awaiting_new_session=true` in config

**Cleanup:**
```bash
# Reset state
cat .config.json | jq '.projects["codogram-testing-area"].threads["null"].awaiting_new_session'
```

---

## TC-SESSIONS-002: /esc sends Escape to tmux

**Tags:** critical, sessions
**Preconditions:** Active tmux session

**Setup:**
```bash
# Ensure tmux exists
tmux has-session -t claude-codogram-testing-area
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/esc")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Confirmation message (e.g., "Escape sent")
- State: Escape key sent to tmux pane

---

## TC-SESSIONS-003: /new alias works

**Tags:** full, sessions
**Preconditions:** Active session

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/new")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=3)
```

**Expected:**
- Same as /clear_context - clears context

---

## TC-SESSIONS-004: /reset_chat restarts Claude

**Tags:** full, sessions
**Preconditions:** Active Claude session

Aliases: `/restart`

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/reset_chat")
# Wait 10s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: "[~] Restarting Claude..." then "[v] Claude ready"
- State: tmux process restarted, session_id=null
