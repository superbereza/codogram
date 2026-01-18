# Activity Indicators E2E Tests

Тесты для thinking status и input suggestions.

**Особенность:** Эти тесты требуют наблюдения пользователя, т.к. MCP не может видеть динамические UI элементы (спиннеры, клавиатуры).

## TC-ACT-001: Thinking status appears

**Precondition:** Claude сессия активна в тестовом чате

**Steps:**
1. `mcp__telegram__send_message(chat_id=TEST_CHAT, message="ultrathink about the meaning of life")`
2. **ASK USER:** "Посмотри в Telegram — видишь сообщение со спиннером? (например '· Thinking… (/esc to interrupt)')"

**Expected:**
- User confirms: сообщение со спиннером появилось

**Result:** PASS если user подтвердил / FAIL если нет

---

## TC-ACT-002: Thinking status updates

**Precondition:** TC-ACT-001 passed, Claude ещё думает

**Steps:**
1. **ASK USER:** "Подожди ~5 секунд. Обновилось время/токены в сообщении со спиннером?"

**Expected:**
- User confirms: время или токены изменились

**Result:** PASS если user подтвердил / FAIL если нет

---

## TC-ACT-003: Thinking status deleted on response

**Precondition:** TC-ACT-002 passed

**Steps:**
1. **ASK USER:** "Когда Claude ответит — сообщение со спиннером удалится?"
2. Дождаться ответа Claude
3. `mcp__telegram__list_messages(chat_id=TEST_CHAT, limit=10)` — проверить что ответ пришёл

**Expected:**
- User confirms: сообщение со спиннером удалилось
- В messages есть ответ Claude

**Result:** PASS если оба условия / FAIL если нет

---

## TC-ACT-004: /esc interrupts thinking

**Precondition:** Claude сессия активна

**Steps:**
1. `mcp__telegram__send_message(chat_id=TEST_CHAT, message="ultrathink very deeply for a long time")`
2. **ASK USER:** "Видишь спиннер? Скажи когда появится"
3. User confirms
4. `mcp__telegram__send_message(chat_id=TEST_CHAT, message="/esc")`
5. **ASK USER:** "Claude прервался? Спиннер исчез?"

**Expected:**
- User confirms: Claude прервался, спиннер удалился

**Result:** PASS если user подтвердил / FAIL если нет

---

## TC-ACT-005: Input suggestion appears

**Precondition:** Claude сессия активна

**Steps:**
1. `mcp__telegram__send_message(chat_id=TEST_CHAT, message="check git status and tell me what you see")`
2. Дождаться ответа Claude
3. **ASK USER:** "После ответа Claude — появилось сообщение '💡' с кнопкой-саджестом внизу экрана?"

**Expected:**
- User confirms: появилась кнопка с предложением (ReplyKeyboard)

**Result:** PASS если user подтвердил / SKIP если саджест не появился (зависит от Claude)

---

## TC-ACT-006: Clicking suggestion sends text

**Precondition:** TC-ACT-005 passed, кнопка видна

**Steps:**
1. **ASK USER:** "Нажми на кнопку-саджест. Что произошло?"

**Expected:**
- User confirms: текст отправился в чат
- User confirms: кнопка исчезла

**Result:** PASS если оба условия / FAIL если нет

---

## Notes

- TC-ACT-005/006 могут быть SKIP если Claude не предложил саджест — это нормально, зависит от контекста
- Для надёжного теста саджестов нужно найти промпт который стабильно их вызывает
