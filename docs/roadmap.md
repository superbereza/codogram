# Telegram Bridge Roadmap

## В работе

- [ ] **Start Claude from Telegram** — запуск Claude по /start вместо ручного запуска
  - Дизайн: `designs/2025-12-25-start-claude-from-telegram.md`
  - Конвенция `~/dev/{project}` + fallback на /register_dir
  - tmux сессии `claude-{project}`

## Выполнено недавно

- [x] **Fix poller duplication** — исправлено дублирование поллеров при /new и рестарте
  - План: `plans/done/2025-12-24-fix-poller-duplication.md`
  - Коммиты: 5ca1e10..90dff32
  - Debug endpoint `/debug` для диагностики

- [x] **Background permission poller** — независимый polling с debounce
  - Дизайн: `designs/2025-12-24-background-permission-poller.md`
  - План: `plans/2025-12-24-background-permission-poller.md`
  - Коммиты: e2b5dbe..804321a

- [x] **Permission content display** — показ полного контента permission + удаление после ответа
  - План: `plans/2025-12-24-permission-content-display.md`
  - Коммиты: d36bb9a..d841c4b

- [x] **Permission detection** — показ permissions с inline кнопками
  - План: `plans/2025-12-23-permission-detection.md`
  - Коммиты: 18eadcf..0b720b3

## Следующее

- [ ] **Forward unhandled commands** — `/команды` без хэндлера прокидывать в Claude как есть
  - Сейчас добавляются в tmux с двумя слэшами, не отправляются
  - Нужен fallback в `on_message` или отдельный хэндлер

- [ ] **Thinking indicator** — показывать когда Claude думает
  - В jsonl есть `type: "thinking"` entries
  - Отправлять "🤔 Thinking..." или подобное

- [ ] **Tool progress display** — показывать прогресс выполнения инструментов
  - Расширить Task 5 в плане permission-detection
  - Сейчас `ToolProgress` парсится, но не отображается (pass)
  - **Инсайт:** В Claude первая строка статична (Task/Tool name), остальные бегут
    ```
    Task(Implement Task 1: Screen Parser)
      ⎿  Read 46 lines
         Read 30 lines
         Waiting…
    ```
  - Из jsonl приходит первая строка — на ней можно якориться

- [ ] **R4: Voice + Multi-project** — голосовые сообщения через Whisper, несколько проектов
  - План: `plans/2025-12-23-telegram-bridge.md` (Release 4)

## Идеи / PoC

- [ ] **Markdown to Telegram converter** — библиотека для конвертации обычного MD в TG-совместимый
  - Таблицы, headers не рендерятся в Telegram
  - Поискать готовые решения (telegramify-markdown, etc.)

- [ ] **tmux-only архитектура** — парсить только tmux вместо jsonl + tmux
  - Дизайн: `designs/telegram-bridge-tmux-only.md`
  - Проще, но хрупче (зависит от формата вывода Claude)

## Выполнено

- [x] R1: Echo Bot + tmux
- [x] R2: jsonl Watcher + Output
- [x] R3.2: Permission display (базовый — без кнопок)
