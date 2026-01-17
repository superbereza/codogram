# Codogram

Telegram bot for managing Claude Code sessions from your phone.

**[Русская версия](README.ru.md)**

## Features

- **Permission prompts** — Yes/No buttons right in Telegram
- **Send messages** — type in Telegram, text goes to Claude
- **Tool calls** — see what Claude is doing in real-time
- **Multi-session** — multiple projects, each in its own topic
- **Git worktrees** — isolated branches with separate directories

## How it works

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│ Claude Code │◄───────►│   Codogram  │◄───────►│  Telegram   │
│   (tmux)    │  tmux   │    (bot)    │   API   │   (phone)   │
└─────────────┘         └─────────────┘         └─────────────┘
```

1. Claude Code runs in a tmux session
2. Codogram monitors `~/.claude/history.jsonl` and tmux
3. Permission prompts are sent to Telegram
4. Your messages are sent back to tmux

## Quick Start

### Option 1: Automatic setup (recommended)

```bash
git clone https://github.com/superbereza/codogram.git
cd codogram
./setup.sh
```

The script will:
- Install Python 3.11, tmux, and Claude Code CLI if needed
- Create virtual environment
- Ask for your Telegram bot token ([@BotFather](https://t.me/BotFather))
- Ask for your Telegram ID ([@userinfobot](https://t.me/userinfobot))
- Create `.env` file

### Option 2: Manual setup

```bash
git clone https://github.com/superbereza/codogram.git
cd codogram

python3 -m venv venv
source venv/bin/activate
pip install -e .

cp .env.example .env
# Edit .env with your TELEGRAM_TOKEN and ADMIN_IDS
```

### Run

```bash
./restart.sh
```

### Use

1. Open tmux and start Claude Code in your project
2. Send `/start` or `/start project_name` to the bot in Telegram
3. Done! Permission prompts will appear in the chat

### Update

```bash
git pull
./restart.sh
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Connect to Claude or show status |
| `/thread` | Create new topic with Claude session |
| `/branch` | Create git worktree + topic (isolated branch) |
| `/finish` | Archive topic or merge branch |
| `/esc` | Cancel current Claude operation (Ctrl+C) |
| `/new` | Start new Claude session (clear context) |
| `/auto_accept` | Toggle auto-accept for permission prompts |
| `/shift_tab` | Cycle Claude approval mode |
| `/verbose` | Toggle verbose output |
| `/settings` | View current settings |
| `/help` | List all commands |

## Requirements

- Python 3.10+
- tmux
- Claude Code CLI

## Documentation

- [Installation Guide](docs/setup.md) — detailed setup instructions
- [CLAUDE.md](CLAUDE.md) — context for Claude sessions

## Limitations

- One Claude per tmux session (split panes not supported)
- cwd is fixed at `/start` (cd not tracked)
- Session detection delay up to 15 seconds

## Contact

Questions, ideas, bugs? Write to [@superbereza](https://t.me/superbereza) on Telegram.

## License

GPL-3.0
