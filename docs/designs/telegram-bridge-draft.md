# Telegram-Claude Bridge — Draft Design

**Статус**: Draft
**Дата**: 2025-12-23

## Цель

Управлять Claude Code с телефона через Telegram. Максимально тонкая прослойка — не дублировать логику Claude Code, только транспорт.

## Требования

### Основные

| Требование | Детали |
|------------|--------|
| Группы = проекты | Разные Telegram группы/чаты = разные рабочие директории |
| 1 группа = 1 tmux | По умолчанию одна сессия на проект |
| Spawn sessions | Можно запустить дополнительные сессии командой |
| Streaming | Редактировать сообщение в реалтайме |
| Voice → text | Whisper для голосовых сообщений |
| Permissions | НЕ скипать — показывать в Telegram для одобрения |
| Chunking | Дробить длинные сообщения (4000 символов лимит) |
| Attach | Можно подключиться к tmux напрямую из терминала |

### Стиль

Использовать символы Claude Code, НЕ emoji:

| Символ | Значение |
|--------|----------|
| `●` | Ожидание/ошибка |
| `◐` | В процессе |
| `✓` | Завершено |
| `⎿` | Продолжение (continuation) |

**Не использовать**: 🔴⚡🌸 и прочие emoji.

## Архитектура

### Рассмотренные варианты

#### 1. Claude Agent SDK (Node.js)

```
Telegram → SDK.query() → Claude API → Response → Telegram
```

**Плюсы**: Официальный SDK, callbacks для permissions
**Минусы**: Нет живой tmux сессии, нельзя attach

#### 2. tmux + парсинг вывода

```
Telegram → tmux send-keys → Claude Code
Claude Code stdout → parse ANSI → Telegram
```

**Плюсы**: Живая сессия, можно attach
**Минусы**: Хрупкий парсинг ANSI, формат может меняться

#### 3. tmux + jsonl (рекомендуется)

```
Telegram → tmux send-keys → Claude Code
~/.claude/projects/<hash>/<session>.jsonl → parse JSON → Telegram
```

**Плюсы**:
- Живая tmux сессия, можно attach
- Структурированный JSON вместо ANSI
- Стабильный формат (внутренний API Claude Code)

**Минусы**:
- Нужно проверить timing записи (realtime или в конце)

### Рекомендуемая архитектура

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│  Telegram   │────▶│  Bridge Server  │────▶│    tmux     │
│   (phone)   │◀────│   (Python)      │◀────│ Claude Code │
└─────────────┘     └─────────────────┘     └─────────────┘
                            │
                            ▼
                    ~/.claude/projects/
                        *.jsonl
```

**Поток данных**:

1. Telegram message → Bridge
2. Bridge → `tmux send-keys "message" Enter`
3. Claude Code работает, пишет в jsonl
4. Bridge watch jsonl → новые строки
5. Parse JSON, detect type:
   - `assistant` + `text` → отправить в Telegram
   - `tool_use` → показать `◐ ожидание permission`
   - `tool_result` → обновить статус
6. Chunking если > 4000 символов
7. Edit message для streaming эффекта

## Компоненты

### 1. Session Manager

```python
class SessionManager:
    """Управление tmux сессиями"""

    def get_or_create(self, project_id: str) -> TmuxSession:
        """1 группа = 1 сессия по умолчанию"""

    def spawn(self, project_id: str) -> TmuxSession:
        """Дополнительная сессия для проекта"""

    def send(self, session: TmuxSession, message: str):
        """tmux send-keys"""

    def attach_info(self, session: TmuxSession) -> str:
        """Инструкция для attach: tmux attach -t ..."""
```

### 2. Output Watcher

```python
class JsonlWatcher:
    """Следит за ~/.claude/projects/*/session.jsonl"""

    async def watch(self, session_id: str) -> AsyncIterator[dict]:
        """Yield новые строки как dict"""

    def detect_state(self, entry: dict) -> State:
        """waiting_permission | processing | complete | idle"""
```

**Формат jsonl (проверено экспериментально):**

```
~/.claude/projects/<project-hash>/<session-id>.jsonl
```

Каждая строка — JSON с полями:
- `type`: "assistant" | "user" | "file-history-snapshot"
- `timestamp`: ISO timestamp
- `message.content[]`: массив с типами:
  - `{"type": "text", "text": "..."}` — текст ответа
  - `{"type": "tool_use", "name": "Bash", "input": {...}}` — вызов инструмента
  - `{"type": "tool_result", "content": "..."}` — результат
  - `{"type": "thinking", "thinking": "..."}` — размышления
- `message.stop_reason`: null (в процессе) | "end_turn" | "tool_use"

### 3. Telegram Handler

```python
class TelegramBridge:
    """Telegram Bot API"""

    async def on_message(self, message: Message):
        """Text или voice → Claude"""

    async def on_voice(self, message: Message):
        """Whisper transcription → on_message"""

    async def stream_response(self, chat_id: int, content: str):
        """Edit message для streaming"""

    async def ask_permission(self, chat_id: int, tool: str) -> bool:
        """Показать permission, ждать ответ"""
```

### 4. Chunker

```python
def chunk_message(text: str, max_len: int = 4000) -> list[str]:
    """
    Приоритет разбиения:
    1. По параграфам (\\n\\n)
    2. По строкам (\\n)
    3. По предложениям (. ! ?)
    4. По словам
    5. Hard split

    Добавляет "[1/5]\\n" префикс
    """
```

## Mapping: Telegram → Project

**Варианты**:

1. **Config file**: `telegram_bridge.yaml`
   ```yaml
   groups:
     -123456789: /home/user/project-a
     -987654321: /home/user/project-b
   ```

2. **Команда в чате**: `/setproject /path/to/project`

3. **По названию группы**: группа "project-a" → `~/dev/project-a`

**Рекомендация**: Config file + команда для override.

## Open Questions

1. ~~**jsonl timing**~~ — **РЕШЕНО: пишется в реалтайме**
   - Каждый chunk (text, tool_use, tool_result, thinking) = отдельная запись
   - Timestamps показывают realtime запись
   - Формат стабильный, структурированный JSON

2. ~~**Permission detection**~~ — **РЕШЕНО: tmux capture-pane**
   - См. секцию "Permission & Progress Detection" ниже

3. **Permission timeout** — сколько ждать ответа?
   - whatsapp-claude-agent использует 5 минут
   - Предлагаю 10 минут (телефон может быть в кармане)

4. **Multiple responses** — Claude иногда даёт варианты ответа
   - Нужно обработать как отдельные сообщения

5. **Session resume** — как передать `--resume`?
   - Автоматически resume последней сессии в группе?

## Permission & Progress Detection

**Проблема**: В jsonl нет информации о том, ждёт ли Claude permission или инструмент выполняется.

**Решение**: `tmux capture-pane` для чтения экрана терминала.

### Когда делать capture-pane

```
jsonl: tool_use  →  [polling capture-pane]  →  tool_result
                         ↓
              показываем progress/permissions
```

1. Видим `tool_use` в jsonl → начинаем polling capture-pane (каждые 0.5-1 сек)
2. Парсим экран, показываем в Telegram
3. Видим `tool_result` в jsonl → останавливаем polling

### Формат permission prompt в терминале

```
Do you want to create test.txt?
❯ 1. Yes
  2. Yes, allow all edits during this session (shift+tab)
  3. Type here to tell Claude what to do differently
Esc to cancel
```

**Маркер permission**: символ `❯` + пронумерованные опции (`1.`, `2.`, etc.)

### Формат progress в терминале

```
● Bash(npm install)
  ⎿  added 150 packages in 3s
     ... (output streaming)
✶ Determining… (esc to interrupt)
```

### Парсинг capture-pane

```python
def parse_tmux_screen(output: str) -> ScreenState:
    """
    Returns:
    - PermissionPrompt(options=["Yes", "Yes, allow all...", ...])
    - ToolProgress(tool="Bash", output="...")
    - Idle()
    """
    if "❯" in output and re.search(r'\d+\.', output):
        # Permission prompt detected
        return parse_permission_options(output)
    elif "✶" in output or "●" in output:
        # Tool in progress
        return parse_tool_progress(output)
    else:
        return Idle()
```

### Telegram UI для permissions

Показываем inline keyboard с опциями:

```
● Write(test.txt)
Create file with "hello world"

[1. Yes] [2. Allow all] [Esc]
```

При нажатии кнопки → `tmux send-keys "1"` или `tmux send-keys Escape`

### tool_result в jsonl

tool_result находится в entries с `type: "user"`:

```json
{
  "type": "user",
  "message": {
    "content": [{
      "type": "tool_result",
      "tool_use_id": "toolu_...",
      "content": "file created successfully"
    }]
  }
}
```

### Streaming текста

**Решение**: НЕ делать streaming для текста.
- Claude Code отдаёт текстовые ответы целиком (stop_reason: "end_turn")
- Streaming нужен только для progress инструментов (через capture-pane)

## Референсы

### Вдохновение (клонированы в tmp/inspiration/)

| Репо | Что взять |
|------|-----------|
| claude-central | Мониторинг jsonl, детекция состояний |
| whatsapp-claude-agent | Permission queue, chunking логика |
| pocketportal | Telegram buttons для permissions |

### Существующий код

| Компонент | Где |
|-----------|-----|
| Whisper transcription | bz-merch-assistant: `ai_bot_core/services/whisper.py` |
| Edit-message streaming | bz-merch-assistant: `ai_bot_core/bot/streaming.py` |

## MVP Scope

**Phase 1 — минимум**:
- [ ] 1 группа = 1 проект (hardcoded config)
- [ ] tmux send-keys для input
- [ ] jsonl watch для output
- [ ] Базовый chunking
- [ ] Статус символы (●◐✓)

**Phase 2**:
- [ ] Voice → Whisper → text
- [ ] Permission handling (не auto-approve)
- [ ] Streaming (edit message)
- [ ] Spawn additional sessions

**Phase 3**:
- [ ] Multiple projects config
- [ ] /attach command (показать tmux attach инструкцию)
- [ ] /status command

## Следующие шаги

1. Проверить jsonl write timing экспериментом
2. Skeleton проекта с aiogram
3. MVP Phase 1
