# /thread Tests

Topic creation and management.

## TC-THREADS-001: /thread shows name prompt

**Tags:** critical, threads
**Preconditions:** In a forum chat

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/thread")
# Wait 2s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=2)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- Message: "Thread name?\n\nSend name or pick random"
- Buttons: [🔮 Magic name], [<<] Go back

## TC-THREADS-002: Magic name creates topic

**Tags:** critical, threads
**Preconditions:** TC-THREADS-001 prompt visible

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="🔮 Magic name")
# Wait 5s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=5)
```

**Expected:**
- Prompt deleted
- Topic created with random name (arcane, mystic, etc.)
- "[v] Claude ready" message appears

## TC-THREADS-003: Cancel button deletes prompt

**Tags:** threads
**Preconditions:** /thread prompt visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/thread")
# Wait 1s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="[<<] Go back")
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=3)
```

**Expected:**
- Prompt message deleted
- No topic created

## TC-THREADS-004: Text input creates topic

**Tags:** critical, threads
**Preconditions:** /thread prompt visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/thread")
# Wait 1s
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="my-custom-topic")
# Wait 5s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=5)
```

**Expected:**
- Topic "my-custom-topic" created
- "[v] Claude ready" message appears

## TC-THREADS-005: /thread with argument creates directly

**Tags:** threads, regression
**Preconditions:** In a forum chat

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/thread direct-topic")
# Wait 5s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=5)
```

**Expected:**
- No prompt shown
- Topic "direct-topic" created directly
- "[v] Claude ready" message appears

## TC-THREADS-006: Invalid name shows error

**Tags:** threads
**Preconditions:** /thread prompt visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/thread")
# Wait 1s
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="!!!")
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=3)
```

**Expected:**
- Error message about invalid name
- No topic created
