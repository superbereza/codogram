# Telegram Bridge Roadmap

## В работе

- [ ] **Permission detection** — показ permissions с inline кнопками
  - План: `plans/2025-12-23-permission-detection.md`

## Следующее

- [ ] **Tool progress display** — показывать прогресс выполнения инструментов
  - Расширить Task 5 в плане permission-detection
  - Сейчас `ToolProgress` парсится, но не отображается (pass)

- [ ] **R4: Voice + Multi-project** — голосовые сообщения через Whisper, несколько проектов
  - План: `plans/2025-12-23-telegram-bridge.md` (Release 4)

## Идеи / PoC

- [ ] **tmux-only архитектура** — парсить только tmux вместо jsonl + tmux
  - Дизайн: `designs/telegram-bridge-tmux-only.md`
  - Проще, но хрупче (зависит от формата вывода Claude)

## Выполнено

- [x] R1: Echo Bot + tmux
- [x] R2: jsonl Watcher + Output
- [x] R3.2: Permission display (базовый — без кнопок)
