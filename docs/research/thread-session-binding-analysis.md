# Thread↔Session Binding: Corner Cases & Solutions

> Анализ проблем привязки Telegram threads к Claude sessions и механизмов их решения

## Проблема

В multi-thread архитектуре (Telegram topics) нужно связать:
- **Telegram thread** (topic в группе)
- **tmux session** (где запущен Claude)
- **Claude session** (session_id в jsonl файлах)

Claude Code **не знает** о tmux sessions и Telegram threads. Это создаёт проблему: как понять какой thread получил новую сессию?

---

## Corner Cases

### 1. Thread Session Mixup (CRITICAL BUG)

**Сценарий:**
```
Thread A: session_id = aaa111
Thread B: session_id = bbb222

User does /new in Thread A → new session ccc333 appears

Bug: Thread B detects "session changed" and loses its binding
```

**Root cause:**
```python
# history_watcher.py:250
new_session_id = find_session_for_project(project.cwd)
# Returns LATEST session for PROJECT, not for THREAD!
```

**Симптомы:**
- Thread теряет session_id (становится null)
- Watcher останавливается
- Сообщения от Claude перестают приходить

**Логи:**
```
session_changed_thread: project=codogram, thread=sublime, old=405fe3e1, new=14c5fa0c
watch_thread_cancelled: thread=sublime
```

---

### 2. Session Discovery for New Thread

**Сценарий:**
```
User creates new topic "feature-x"
User sends message in Telegram
Bot needs to find which Claude session belongs to this thread
```

**Проблема:** Новый thread не имеет session_id. Как найти правильную сессию?

---

### 3. /compact, /new, /clear Detection

**Сценарий:**
```
User does /compact in tmux directly (not through bot)
Session may or may not change
Bot needs to detect and handle this
```

**Findings:**
| Command | New session? | Detectable? |
|---------|--------------|-------------|
| `/new` | YES | Via history.jsonl sessionId change |
| `/clear` | YES | Via history.jsonl sessionId change |
| `/compact` | NO | Via `summary` record in session jsonl |

---

### 4. Multiple Sessions Same Project

**Сценарий:**
```
Project: /home/user/dev/myproject
Thread A (main): session aaa
Thread B (feature): session bbb
Thread C (bugfix): session ccc

All sessions are in same project directory
history.jsonl shows only the LATEST session
```

**Проблема:** `find_session_for_project()` вернёт только последнюю сессию, не различая threads.

---

### 5. tmux Session Dies

**Сценарий:**
```
Thread A has active session
User kills tmux session or it crashes
Bot should detect and notify user
```

**Текущее решение:** HistoryWatcher проверяет `tmux.exists()` каждые 15 сек.

---

### 6. Bot Restart / State Loss

**Сценарий:**
```
Bot crashes/restarts
Need to restore thread↔session bindings
```

**Текущее решение:** Bindings сохраняются в `.config.json` и восстанавливаются при старте.

---

## Механизмы решения

### Mechanism 1: history.jsonl Polling (CURRENT)

**Как работает:**
1. Каждые 15 сек читаем history.jsonl
2. Находим последнюю сессию для каждого project (cwd)
3. Если session_id изменился → обновляем binding

**Плюсы:**
- Простая реализация
- Не требует hooks
- Работает "из коробки"

**Минусы:**
- **НЕ различает threads!** (root cause бага)
- Latency 15 сек
- Не знает какой thread инициировал смену

**Статус:** Используется, но вызывает Thread Session Mixup bug

---

### Mechanism 2: Claude SessionStart Hook

**Как работает:**
1. Claude вызывает hook при старте сессии
2. Hook получает session_id, cwd
3. Hook делает HTTP POST на HookServer
4. HookServer привязывает сессию к thread по tmux session name

**Плюсы:**
- Instant detection (без polling)
- Точное время события

**Минусы:**
- Hook НЕ получает tmux session name (нужно определять через `tmux display-message`)
- Требует настройки hooks в settings.json
- Дополнительная инфраструктура (HTTP server)

**Статус:** Спроектировано, не реализовано

---

### Mechanism 3: Content Matching (Fallback)

**Как работает:**
1. Читаем последнее сообщение assistant из session jsonl
2. Делаем tmux capture-pane для каждого unbound thread
3. Если контент совпадает → это наш thread

**Плюсы:**
- Работает без hooks
- Fallback для edge cases

**Минусы:**
- Ненадёжно (контент может не совпадать)
- Медленно (нужно capture всех tmux panes)
- Сложная логика

**Статус:** Спроектировано как fallback, не реализовано

---

### Mechanism 4: Telegram Commands (RECOMMENDED)

**Как работает:**
1. Пользователь делает `/new` или `/clear` через Telegram бот
2. Бот знает какой thread → ставит `awaiting_new_session = true`
3. Бот отправляет команду в tmux
4. При появлении новой сессии → привязывает к ожидающему thread

**Плюсы:**
- Простая и надёжная логика
- Не требует hooks
- Бот всегда знает какой thread
- Никакого content matching

**Минусы:**
- Не работает если user делает /new напрямую в tmux
- Требует дисциплины пользователя

**Статус:** Рекомендуется к реализации

---

### Mechanism 5: User Message Fingerprinting

**Как работает:**
1. При отправке сообщения через Telegram сохраняем `last_sent_message`
2. При появлении новой сессии ищем это сообщение в jsonl
3. Если нашли → это сессия нашего thread

**Плюсы:**
- Работает для новых threads
- Не требует hooks

**Минусы:**
- Не работает для /new, /clear (нет user message)
- Сложная логика поиска
- Race conditions

**Статус:** Частично реализовано в `poll_for_session_thread()`

---

## Текущая архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                     Telegram Bot                             │
│  /start → discover tmux → start polling                     │
│  on_message → send to tmux → wait for session binding       │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌─────────────────────┐    ┌─────────────────────────────────┐
│  PermissionPoller   │    │        HistoryWatcher           │
│  (tmux polling)     │    │   (history.jsonl polling 15s)   │
│  - detect prompts   │    │   - detect session changes      │
│  - show buttons     │    │   - CAUSES MIXUP BUG!           │
└─────────────────────┘    └─────────────────────────────────┘
                                        │
                                        ▼
                           ┌─────────────────────────────────┐
                           │   check_session_for_thread()    │
                           │   - find_session_for_project()  │
                           │   - WRONG: returns latest       │
                           │     session for PROJECT         │
                           └─────────────────────────────────┘
```

**Проблема:** `check_session_for_thread()` использует `find_session_for_project()` который не различает threads.

---

## Рекомендуемое решение

### Quick Fix (немедленно)

**Удалить `check_session_for_thread()` вызов в bot.py:1388-1389**

Это остановит Thread Session Mixup bug. Threads будут сохранять свои session bindings.

### Long-term Solution

1. **Добавить `/new` и `/clear` команды в Telegram бот**
   - Бот отправляет команду в tmux
   - Ставит `awaiting_new_session = true` для thread
   - При появлении новой сессии → привязывает

2. **Убрать `check_session_for_thread()` полностью**
   - Не нужен если управляем через Telegram команды

3. **Оставить `poll_for_session_thread()` для новых threads**
   - Работает через user message fingerprinting
   - Нужен только при первом binding

### Архитектура после фикса

```
┌─────────────────────────────────────────────────────────────┐
│                     Telegram Bot                             │
│  /new, /clear → set awaiting_new_session → tmux send-keys  │
│  on_message → send to tmux                                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌─────────────────────┐    ┌─────────────────────────────────┐
│  PermissionPoller   │    │        HistoryWatcher           │
│  (unchanged)        │    │   - detect new sessions         │
│                     │    │   - bind to awaiting thread     │
│                     │    │   - NO check_session_for_thread │
└─────────────────────┘    └─────────────────────────────────┘
```

---

## Edge Cases после фикса

### User does /new in tmux directly

**Риск:** Бот не знает что thread ждёт новую сессию.

**Решение:** Забить. Это редкий случай. User может сделать `/start` в Telegram чтобы rebind.

### Multiple threads awaiting

**Риск:** Две threads ждут новую сессию одновременно.

**Решение:** Привязывать к thread по tmux session name (каждый thread имеет свой tmux).

---

## Changelog

- 2025-12-29: Initial analysis based on debugging session
- Root cause identified: `find_session_for_project()` returns project-level, not thread-level session
