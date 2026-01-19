# Codogram

Telegram бот для управления Claude Code сессиями с телефона.

**[English version](README.md)**

## Возможности

- **Permission prompts** — кнопки Yes/No прямо в Telegram
- **Отправка сообщений** — пишешь в Telegram, текст уходит в Claude
- **Tool calls** — видишь что делает Claude в реальном времени
- **Multi-session** — несколько проектов, каждый в своём топике
- **Git worktrees** — изолированные ветки с отдельными директориями
- **Голосовые сообщения** — транскрибируются через Whisper (опционально)

## Как это работает

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│ Claude Code │◄───────►│   Codogram  │◄───────►│  Telegram   │
│   (tmux)    │  tmux   │    (bot)    │   API   │   (phone)   │
└─────────────┘         └─────────────┘         └─────────────┘
```

1. Claude Code работает в tmux сессии
2. Codogram мониторит `~/.claude/history.jsonl` и tmux
3. Permission prompts отправляются в Telegram
4. Твои сообщения отправляются обратно в tmux

## Быстрый старт

### Вариант 1: Автоматическая установка (рекомендуется)

```bash
git clone https://github.com/superbereza/codogram.git
cd codogram
./setup.sh
```

Скрипт:
- Установит Python 3.11, tmux и Claude Code CLI (если нужно)
- Создаст виртуальное окружение
- Спросит токен Telegram бота ([@BotFather](https://t.me/BotFather))
- Спросит твой Telegram ID ([@userinfobot](https://t.me/userinfobot))
- Спросит рабочую директорию (где твои git проекты)
- Опционально настроит Whisper для голосовых сообщений
- Создаст `.env` файл

### Вариант 2: Ручная установка

```bash
git clone https://github.com/superbereza/codogram.git
cd codogram

python3 -m venv venv
source venv/bin/activate
pip install -e .

cp .env.example .env
# Отредактируй .env — впиши TELEGRAM_TOKEN и ADMIN_IDS
```

### Запусти

```bash
./stop-and-restart.sh
```

### Используй

Отправь `/start` боту — он проведёт тебя через настройку.

### Обновление

```bash
git pull
./stop-and-restart.sh
```

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Подключиться к Claude или показать статус |
| `/thread` | Создать новый топик с Claude сессией |
| `/branch` | Создать git worktree + топик (изолированная ветка) |
| `/finish` | Архивировать топик или смержить ветку |
| `/esc` | Отменить текущую операцию Claude (Ctrl+C) |
| `/new` | Начать новую сессию Claude (очистить контекст) |
| `/auto_accept` | Включить/выключить авто-подтверждение промптов |
| `/shift_tab` | Переключить режим подтверждений Claude |
| `/verbose` | Включить/выключить подробный вывод |
| `/settings` | Показать текущие настройки |
| `/help` | Список всех команд |

## Требования

- Python 3.10+
- tmux
- Claude Code CLI

## Документация

- [Установка](docs/setup.ru.md) — подробная инструкция
- [CLAUDE.md](CLAUDE.md) — контекст для Claude сессий

## Решение проблем

**Бот игнорирует сообщения (но команды работают)?**

Отключи privacy mode: [@BotFather](https://t.me/BotFather) → `/setprivacy` → выбери бота → `Disable`

## Ограничения

- Один Claude на tmux сессию (split panes не поддерживаются)
- cwd фиксируется при `/start` (cd не отслеживается)
- Обнаружение сессий с задержкой до 15 сек

## Удаление

Просто удали папку codogram — всё (включая venv) внутри:

```bash
rm -rf codogram
```

## Контакт

Вопросы, идеи, баги? Пиши [@superbereza](https://t.me/superbereza) в Telegram.

## License

GPL-3.0
