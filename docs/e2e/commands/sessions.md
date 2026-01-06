# /new, /clear, /esc, /resume Tests

## TC-SESSIONS-001: /new creates new session

**Tags:** critical, sessions
**Preconditions:** Active session exists

**Setup:**
```bash
# Ensure active session
cat .config.json | jq '.projects["codogram-testing-area"].threads["null"].session_id'
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/new")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=3)
```

**Expected:**
- UI: "New session requested" or similar
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

## TC-SESSIONS-003: /clear resets session state

**Tags:** full, sessions
**Preconditions:** Active session

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/clear")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=3)
```

**Expected:**
- UI: "Session cleared" or similar
- State: `session_id=null`, `awaiting_new_session=true`

---

## TC-SESSIONS-004: /resume explicit resume

**Tags:** full, sessions, resume
**Preconditions:** session_id exists, tmux not running

**Setup:**
```bash
# Kill tmux but keep session_id
tmux kill-session -t claude-codogram-testing-area 2>/dev/null || true
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/resume")
# Wait 20s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: "[~] Resuming session" then Connected
- State: Same session_id, tmux running
