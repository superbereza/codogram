# /thread Tests

Topic creation and management.

## TC-THREADS-001: /thread creates topic

**Tags:** critical, threads
**Preconditions:** In a forum chat

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/thread test-e2e-topic")
# Wait 5s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=3)
mcp__telegram__list_topics(chat_id=-1003356094635)
```

**Expected:**
- UI: "Topic created" or similar confirmation
- State: New topic visible in list_topics, registered in .config.json

**Cleanup:**
```bash
# Note the topic ID for cleanup
cat .config.json | jq '.projects["codogram-testing-area"].threads | to_entries | .[] | select(.value.name == "test-e2e-topic")'
```
