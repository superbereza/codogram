# Codogram

Telegram бот для управления Claude Code сессиями с телефона.

**[English version](README.md)**

## Возможности

- **Permission prompts** — кнопки Yes/No прямо в Telegram
- **Отправка сообщений** — пишешь в Telegram, текст уходит в Claude
- **Tool calls** — видишь что делает Claude в реальном времени
- **Multi-session** — несколько проектов, каждый в своём топике
- **Git worktrees** — изолированные ветки с отдельными директориями

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
./restart.sh
```

### Используй

1. Открой tmux и запусти Claude Code в нужном проекте
2. В Telegram отправь боту `/start` или `/start project_name`
3. Готово! Permission prompts будут приходить в чат

### Обновление

```bash
git pull
./restart.sh
```

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Подключить текущий проект |
| `/start <name>` | Подключить проект по имени |
| `/stop` | Отключить проект |
| `/status` | Показать статус |
| `/my_chat_id` | Узнать свой chat ID |
| `/thread_create` | Создать новый топик с Claude сессией |
| `/branch_create` | Создать git worktree + топик (изолированная ветка) |
| `/branch_create <name>` | Создать worktree с указанным именем ветки |
| `/branch_finish` | Смержить ветку и удалить worktree |

## Требования

- Python 3.10+
- tmux
- Claude Code CLI

## Документация

- [Установка](docs/setup.ru.md) — подробная инструкция
- [CLAUDE.md](CLAUDE.md) — контекст для Claude сессий

## Ограничения

- Один Claude на tmux сессию (split panes не поддерживаются)
- cwd фиксируется при `/start` (cd не отслеживается)
- Обнаружение сессий с задержкой до 15 сек

## Контакт

Вопросы, идеи, баги? Пиши [@superbereza](https://t.me/superbereza) в Telegram.

## License

GPL-3.0
