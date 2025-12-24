# Telegram Bridge Roadmap

## Backlog

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

### Bot command menu
Прописать команды в Telegram menu через setMyCommands:
- /esc — отправить Escape
- /shift_tab — отправить Shift+Tab (навигация по опциям)
- /status — показать активную сессию
- /register_dir — привязать чат к папке

### Self-hosting exception
Когда telegram-bridge станет отдельным проектом:
- Базовая сессия чат-бота должна быть связана с папкой самого telegram-bridge
- Это позволит управлять ботом через самого себя
- Исключение из обычной логики project_name → chat
