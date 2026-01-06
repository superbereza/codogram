# History Watcher Tests

Tool call output delivery to Telegram.

## TC-WATCHER-001: Tool call appears in correct topic

**Tags:** smoke, critical, watcher
**Preconditions:** Active session in topic, Claude running

**Setup:**
```bash
# Ensure session bound to topic
cat .config.json | jq '.projects["codogram-testing-area"].threads["303"]'
```

**Steps:**
```python
# Send message that triggers tool call (e.g., ask to read a file)
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="Read /tmp/test.txt")
# Wait 30s for Claude to process
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=303, limit=10)
```

**Expected:**
- UI: Tool call output appears in topic 303 (contains file content or error)
- State: Watcher task running for this thread

---

## TC-WATCHER-002: Tool call NOT in other topics (isolation)

**Tags:** critical, watcher, isolation
**Preconditions:** Two active topics with different sessions

**Setup:**
```bash
# Ensure two topics exist with sessions
# Topic A: 303 (test-regular-topic)
# Topic B: 222 (test-resume)
cat .config.json | jq '.projects["codogram-testing-area"].threads | keys'
```

**Steps:**
```python
# Send message to Topic A
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="Echo test isolation")
# Wait 30s
# Check Topic B - should NOT have the output
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=222, limit=5)
# Check Topic A - SHOULD have the output
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=303, limit=5)
```

**Expected:**
- UI: Output ONLY in Topic A (303), NOT in Topic B (222)
- State: Each topic has independent watcher

---

## TC-WATCHER-003: Long tool output chunking

**Tags:** full, watcher
**Preconditions:** Active session

**Steps:**
```python
# Ask Claude to output something long (>4096 chars)
mcp__telegram__send_message(chat_id=-1003356094635, message="List all files in /usr recursively, first 200 lines")
# Wait 60s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=10)
```

**Expected:**
- UI: Multiple messages if output > 4096 chars
- State: All chunks delivered in order
