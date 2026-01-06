# Message Forwarding Tests

User messages to Claude.

## TC-MESSAGES-001: Message reaches Claude

**Tags:** smoke, critical, messages
**Preconditions:** Active session with tmux

**Setup:**
```bash
# Ensure session is bound
tmux has-session -t claude-codogram-testing-area
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="Hello from E2E test")
# Wait 5s
# Check tmux for the message
```

```bash
tmux capture-pane -t claude-codogram-testing-area -p | grep "Hello from E2E test"
```

**Expected:**
- UI: Message sent confirmation (or no error)
- State: Message visible in tmux pane

---

## TC-MESSAGES-002: Message isolated to correct thread

**Tags:** critical, messages, isolation
**Preconditions:** Two active topics with different tmux sessions

**Setup:**
```bash
# Two topics with their own tmux
# Topic A: 303 -> claude-codogram-testing-area-test-regular-topic
# Topic B: 222 -> claude-codogram-testing-area-test-resume
```

**Steps:**
```python
# Send message to Topic A
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="Isolation test Topic A")
# Wait 5s
```

```bash
# Check Topic A's tmux - should have message
tmux capture-pane -t claude-codogram-testing-area-test-regular-topic -p | grep "Isolation test Topic A"
# Check Topic B's tmux - should NOT have message
tmux capture-pane -t claude-codogram-testing-area-test-resume -p | grep "Isolation test Topic A" && echo "FAIL: leaked" || echo "PASS: isolated"
```

**Expected:**
- UI: Message only in Topic A's tmux
- State: Messages routed to correct tmux session
