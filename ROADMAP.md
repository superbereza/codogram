# Telegram Bridge Roadmap

## Done

### Bot command menu ✓
Команды в Telegram menu через setMyCommands.

## Backlog

### Voice → Whisper
Голосовые сообщения через Whisper transcription:
- Используем существующий код из bz-merch-assistant
- `ai_bot_core/services/whisper.py`

### Session management (spawn, change, resume)
Управление сессиями в одном проекте:
- Spawn: запустить дополнительную сессию
- Change: переключиться на другую сессию
- Resume: `--resume` для продолжения предыдущей
- UI: команды или inline кнопки

### Multi-session in one chat
Несколько worktree сессий в одном чате с возможностью переключения.
- Варианты: треды, префиксы, inline кнопки
- Требует: UI для переключения между сессиями

### Activity indicators
Отображение что Claude думает/работает:
- "thinking..." когда Claude обрабатывает
- Throbber/typing indicator
- Слова типа "Hmm", "Let me think"

### Tool results formatting
Красивое форматирование результатов тулов:
- Syntax highlighting для кода
- Collapsible для длинных выводов
- Превью для файлов

### Hidden tools filtering
Не показывать тулы которых нет в CLI интерфейсе:
- TodoWrite
- Другие internal тулы
- Нужно исследовать какие именно скрыты

### Self-hosting exception
Когда telegram-bridge станет отдельным проектом:
- Базовая сессия чат-бота должна быть связана с папкой самого telegram-bridge
- Это позволит управлять ботом через самого себя
- Исключение из обычной логики project_name → chat

## PoC / Research

### telegram-bridge-tmux-only
Эксперимент: использовать только tmux capture-pane без jsonl.
- См. `docs/designs/telegram-bridge-tmux-only.md`
- Плюсы: проще, не зависит от внутреннего формата Claude
- Минусы: парсинг ANSI, нестабильно
