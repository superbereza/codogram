# Codogram - Claude Runtime Context

## What it does

Telegram bot for managing Claude Code sessions through Telegram:
- Shows permission prompts with Yes/No buttons
- Sends messages to tmux session running Claude
- Monitors tool calls and displays them in Telegram

## Architecture

**Session discovery:** history.jsonl polling (not hooks)
**Refresh interval:** 15s
**Cleanup threshold:** 30 days (by jsonl mtime)

### How sessions are discovered

1. User sends `/start` or `/start <project_name>` in Telegram
2. Bot discovers tmux session by scanning all tmux panes for matching cwd
3. Bot polls `~/.claude/history.jsonl` every 15s to find session_id for that project
4. Bot monitors both tmux (for permission prompts) and jsonl (for tool calls)

### Session lifecycle

- **Registration**: `/start` command discovers tmux + polls for session_id
- **Updates**: history.jsonl polling detects session changes (/new, /resume, /compact)
- **Cleanup**: Projects with jsonl mtime > 30 days are removed

## Key files

```
agent-tools/codogram/
├── .env                      # TELEGRAM_TOKEN, ADMIN_IDS, BASE_DIR
├── .config.json              # Projects + chat mapping (auto-created)
├── src/codogram/
│   ├── main.py               # Bot entry point
│   ├── config.py             # Settings + config persistence
│   ├── session_manager.py    # ProjectManager - project state
│   ├── history_reader.py     # Parse ~/.claude/history.jsonl
│   ├── permission_poller.py  # Poll tmux for permission prompts
│   ├── watcher.py            # Monitor jsonl for tool calls
│   ├── bot.py                # Telegram command handlers
│   ├── tmux.py               # Tmux session interaction
│   └── screen.py             # Parse tmux screen content
└── restart.sh                # Restart bot script
```

## Usage

### Start bot

```bash
./restart.sh
```

### Register project

```bash
# In Telegram:
/start              # Auto-detect or ask for project name
/start myproject    # Start with specific project
```

### Debugging

```bash
# Check if running
ps aux | grep codogram

# View logs
tail -f ~/dev/personal-agent/tmp/codogram-logs/poller-debug.log
tail -f ~/dev/personal-agent/tmp/codogram-logs/poller-sent.log

# View config
cat .config.json | jq
```

## Constraints

- One Claude per tmux session (split panes not supported)
- cwd is fixed at `/start` (cd commands not tracked)
- Session changes detected within 15s (polling interval)
- Requires tmux session to be running in specified directory

## Deprecated features

- **Hooks**: `hooks/session-start.sh` and `hooks/session-end.sh` do nothing (kept for backwards compat)
- **HTTP server**: Removed in favor of history.jsonl polling
- **settings.json hooks**: No longer needed

## See also

- `docs/setup.md` - Installation and setup guide
- `docs/ONBOARDING.md` - Detailed onboarding for new Claude sessions
- `docs/ROADMAP.md` - Future features and improvements
