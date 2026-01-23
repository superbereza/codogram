# /new_chat Tests

Unified chat creation (topic + Claude session).

## TC-NEWCHAT-001: /new_chat shows context + choice

**Tags:** critical, new_chat
**Preconditions:** In a git repo forum chat (General topic)

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/new_chat")
# Wait 2s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=2)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- Message contains: "[?] Creating chat from:" with directory and branch
- Buttons: [Create here], [Create isolated], [<<] Go back

## TC-NEWCHAT-002: Create here shows name prompt

**Tags:** critical, new_chat
**Preconditions:** TC-NEWCHAT-001 prompt visible

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Create here")
# Wait 2s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=2)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- Message: "Chat name?\n\nSend name or pick random"
- Buttons: [🔮 Magic name], [<<] Go back

## TC-NEWCHAT-003: Create isolated shows name prompt

**Tags:** critical, new_chat
**Preconditions:** TC-NEWCHAT-001 prompt visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/new_chat")
# Wait 1s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Create isolated")
# Wait 2s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=2)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- Message: "Chat name?\n\nSend name or pick random"
- Buttons: [🔮 Magic name], [<<] Go back

## TC-NEWCHAT-004: Magic name creates chat

**Tags:** critical, new_chat
**Preconditions:** Name prompt visible (after "Create here")

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="🔮 Magic name")
# Wait 5s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=5)
```

**Expected:**
- Prompt edited to "[~] Creating chat `{name}`..."
- Topic created with random name
- "[v] Chat `{name}` created" message appears

## TC-NEWCHAT-005: Text input creates chat

**Tags:** critical, new_chat
**Preconditions:** Name prompt visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/new_chat")
# Wait 1s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Create here")
# Wait 1s
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="my-test-chat")
# Wait 5s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=5)
```

**Expected:**
- Topic "my-test-chat" created
- "[v] Chat `my-test-chat` created" message appears

## TC-NEWCHAT-006: Cancel deletes prompt

**Tags:** new_chat
**Preconditions:** /new_chat prompt visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/new_chat")
# Wait 1s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="[<<] Go back")
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=3)
```

**Expected:**
- Prompt message deleted
- No topic created

## TC-NEWCHAT-007: Uncommitted changes shows options

**Tags:** new_chat
**Preconditions:** Git repo with uncommitted changes

**Steps:**
```python
# First ensure there are uncommitted changes in main repo
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/new_chat")
# Wait 1s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Create isolated")
# Wait 1s
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="new-branch")
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- Message: "[!] Uncommitted changes detected"
- Buttons: [Create from last commit], [Commit first], [<<] Go back

## TC-NEWCHAT-008: /thread alias works

**Tags:** new_chat, aliases
**Preconditions:** In a forum chat

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/thread")
# Wait 2s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=2)
```

**Expected:**
- Shows same context + choice flow as /new_chat
- Message contains: "[?] Creating chat from:"

## TC-NEWCHAT-009: /branch alias works

**Tags:** new_chat, aliases
**Preconditions:** In a git repo forum chat

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/branch")
# Wait 2s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=2)
```

**Expected:**
- Shows same context + choice flow as /new_chat
- Message contains: "[?] Creating chat from:"

## TC-NEWCHAT-010: /nc alias works

**Tags:** new_chat, aliases
**Preconditions:** In a forum chat

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/nc")
# Wait 2s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=2)
```

**Expected:**
- Shows same context + choice flow as /new_chat
- Message contains: "[?] Creating chat from:"

## TC-NEWCHAT-011: Invalid name shows error

**Tags:** new_chat
**Preconditions:** Name prompt visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/new_chat")
# Wait 1s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Create here")
# Wait 1s
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="!!!")
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=3)
```

**Expected:**
- Error message: "[x] Invalid name"
- No topic created

---

## TC-NEWCHAT-012: /new_chat in non-forum group shows explanation

**Tags:** critical, new_chat
**Preconditions:** Registered project in a non-forum supergroup (topics not enabled)

**Steps:**
```python
mcp__telegram__send_message(chat_id=NON_FORUM_GROUP_ID, message="/new_chat")
# Wait 2s
mcp__telegram__get_messages(chat_id=NON_FORUM_GROUP_ID, page_size=2)
```

**Expected:**
- UI: "[!] Topics required" message
- UI: Instructions how to enable topics:
  - "To enable:"
  - "1. Open group settings (tap group name)"
  - "2. Topics → Enable"
- State: No topic created (can't create topics without forum mode)
