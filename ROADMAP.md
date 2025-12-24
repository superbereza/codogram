# Telegram Bridge Roadmap

## Done

### Bot command menu ✓
Команды в Telegram menu через setMyCommands.

## Backlog

### Voice → Whisper
Голосовые сообщения через Whisper transcription:
- Используем существующий код из bz-merch-assistant
- `ai_bot_core/services/whisper.py`

### Session management
Управление несколькими сессиями в одном проекте:
- Spawn: запустить дополнительную сессию (worktree)
- Change: переключиться на другую сессию
- Resume: `--resume` для продолжения предыдущей
- UI: команды или inline кнопки для переключения

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

### /shift_tab command
Команда для переключения режима approval:
- Отправляет Shift+Tab в tmux
- Репортит изменение режима: "Allow once → Allow for session"
- Парсит текущий выбор из tmux capture-pane

### Self-hosting: default chat = bot project
Дефолтный личный чат с ботом связан с папкой telegram-bridge:
- Позволяет управлять ботом через самого себя
- Не нужно создавать отдельную группу для разработки бота

## PoC / Research

### telegram-bridge-tmux-only
Эксперимент: использовать только tmux capture-pane без jsonl.
- См. `docs/designs/telegram-bridge-tmux-only.md`
- Плюсы: проще, не зависит от внутреннего формата Claude
- Минусы: парсинг ANSI, нестабильно
