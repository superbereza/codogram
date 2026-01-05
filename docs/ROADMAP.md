# Codogram Roadmap

[Русская версия](ROADMAP.ru.md)

## Done

### Codogram extraction
- Extracted from personal-agent to standalone repo
- Renamed package telegram_bridge → codogram
- Full git history preserved (242 commits)
- GitHub: superbereza/codogram

### Core
- tmux send-keys for input
- jsonl watch for output
- Chunking (4000 chars)

### Multi-session architecture
- Single bot process for multiple Claude sessions
- history.jsonl polling for session discovery (not hooks)
- Project → Chat mapping
- Git worktree support (resolves project name)
- Auto-detect project name from chat title

### Permission handling
- Background poller for permission prompts
- Parse content from tmux capture-pane
- Inline keyboard with options
- Delete messages after response

### Interactive prompts
- Claude's clarifying questions with option buttons (plan mode → AskUserQuestion)

### Multi-admin support
- ADMIN_IDS comma-separated in .env
- /my_chat_id command for everyone

### Bot command menu
- /start, /my_chat_id, /register_dir, /esc in Telegram menu

### Session binding
- Bind session by matching message text
- poll_for_session() to find new session
- is_claude_ready() check for Claude TUI readiness
- Doom-guy loading animation on startup

### Multi-session topics
- Telegram Forum Topics: each topic = separate Claude session
- ThreadInfo dataclass for per-thread state
- `/thread_create [name]` — create new topic with Claude
- `/thread_delete` — close topic and kill tmux
- Magic names for auto-naming (arcane, mystic, celestial...)
- Thread-specific watcher and permission poller
- Session binding by user message for each thread
- tmux died detection with notification in topic
- /resume blocking in multi-session mode

### Telegram Rate Limiter
- TelegramQueue class with FIFO queue to prevent 429 (flood control)
- OutgoingBatch for message grouping
- enqueue() returns message IDs for cleanup
- enqueue_nowait() for fire-and-forget
- Retry without parse_mode on Markdown errors

### Markdown underscore escaping
- Telegram interprets `_text_` as italic, breaking snake_case
- Escape `_` → `\_` outside code blocks before sending
- Regex-based, applied centrally in telegram_queue.py

### Security improvements
- shell=False in all subprocess calls (prevents shell injection)
- Project name validation (alphanumeric, dash, underscore only)
- Unified logging via python logging module

### Project initialization wizard
Interactive project initialization on `/start`:
- **Existing local repo** — connect to existing git repository
- **Clone from GitHub** — `git clone <url>` + connect
- **New repo** — `git init` + `gh repo create` + connect
- Inline buttons for option selection
- Auto-create tmux session in selected directory

### Thread session mixup fix
- Bug: creating new session in one topic caused other topics to lose binding
- Solution: Session Binder — `/new`, `/clear` commands + `awaiting_new_session` flag
- See [docs/bugs/fixed/2025-12-29-session-binding-race-condition.md](bugs/fixed/2025-12-29-session-binding-race-condition.md)

### Interactive setup script
- `./setup.sh` — interactive dependency installation
- OS detection (Linux/macOS)
- Interactive selector (numbers for toggle, works in Docker)
- Check and install: python3, brew (macOS), tmux, git, gh, claude
- Create venv, pip install
- Configure .env (bot token, admin ID)
- See [docs/designs/done/2025-12-30-setup-script.md](designs/done/2025-12-30-setup-script.md)

### Git worktree isolation
Isolated branches with separate directories:
- `/branch_create [name]` — create worktree + topic + Claude session
- `/branch_finish` — merge branch, delete worktree and topic
- Unified thread-first flow: topic created first, statuses go there
- Magic names with suffix fallback (arcane-2, arcane-3...)
- See [docs/designs/done/2025-12-30-git-worktree-support.md](designs/done/2025-12-30-git-worktree-support.md)

### Open source release
- LICENSE file (GPL v3)
- Public repository

### Auto-accept mode
Automatic permission prompt confirmation:
- `/auto_accept` — toggle on/off
- `/auto_accept reset all` — reset all settings
- Per-thread/per-project settings
- Skips session-wide permissions ("allow all", "for session")
- Notifications via TelegramQueue
- `/settings` and `/help` commands

### Queue-level chunking
Centralized message chunking in TelegramQueue:
- Messages >4000 chars automatically split
- Removed duplicate code from watcher.py and permission_poller.py
- See [docs/designs/done/2026-01-03-queue-level-chunking.md](designs/done/2026-01-03-queue-level-chunking.md)

### Telegramify-markdown integration
Full GFM → MarkdownV2 conversion using telegramify-markdown library:
- Claude generates GFM Markdown (headers, **bold**, lists)
- telegramify-markdown converts to Telegram MarkdownV2
- Centralized conversion in telegram_queue.py
- Fallback to plain text on parse errors
- See [docs/designs/done/2025-01-04-telegramify-markdown-integration.md](designs/done/2025-01-04-telegramify-markdown-integration.md)

### Bot architecture refactoring
Layered architecture replacing monolithic bot.py (1500+ lines → 0):
- **handlers/** — Telegram command handlers (start, sessions, threads, branches, settings, messages, permissions)
- **services/** — Business logic (start_flow, branch, message_router, launch)
- **middleware/** — AdminMiddleware for global admin protection
- **domain/** — Models, validators, FSM states
- **adapters/** — telegram.py (send_with_retry)
- TelegramQueue injected via aiogram DI
- StartFlowService with FlowAction/FlowResult pattern
- 236 tests, E2E regression testing via Telegram MCP
- See [docs/designs/done/2025-12-27-bot-refactoring/](designs/done/2025-12-27-bot-refactoring/)

## Backlog

### MCP trust prompt support
Detect MCP server trust prompts (box-style UI):
- Different from standard prompts: `❯` on separate line, options around it
- Box characters `│` and `╰────╯` border
- "Enter to confirm · Esc to reject" footer
- Need careful parsing to avoid false positives on numbered lists
- See failed attempt: 2026-01-04 (broke permission detection everywhere)

### Claude exit detection
Detect when Claude exits normally (not crash):
- Show `[~] Claude exited. Use /start to restart.` notification
- Detect shell prompt after Claude UI disappears
- Must track `claude_was_active` to avoid false positives on startup
- Must distinguish shell prompt `❯` from Claude selector `❯ 1. Yes`
- See reverted attempt: 8b6baf8 (had issues with false positives)

### Menu redesign
Reorganize bot commands for better usability:
- Group commands by purpose (everyday, create, complete, settings)
- Short aliases: `/thread`, `/branch`, `/finish`
- Unified `/finish` for both worktree and regular topics
- Archive topics instead of delete (close + icon)
- See [docs/designs/2025-01-03-menu-redesign.md](designs/2025-01-03-menu-redesign.md)

### Session resume by session_id
Resume Claude session after crash or archived topic restore:
- Store session_id in ThreadInfo
- On /start in archived topic or after crash: `claude --resume <session_id>`
- Preserves conversation context instead of starting fresh

### GitHub Actions CI
- Workflow for running tests on PR
- pytest + type checking

### Migrate strings to strings.py
Move all hardcoded strings to `src/codogram/strings.py`:
- bot.py — main volume (~50 strings)
- launch_animation.py — startup statuses
- history_watcher.py — notifications
- keyboards.py — buttons
- start_flow.py — wizard buttons
- See `docs/specs/tone-of-voice.md` for guidelines

### Voice → Whisper
Voice messages via Whisper transcription:
- Use existing code from bz-merch-assistant
- `ai_bot_core/services/whisper.py`

### Pin startup message
Pin message on session start:
- `Claude started in claude-codogram-sublime`
- `Connect: tmux attach -t claude-codogram-sublime`
- Unpin previous on restart

### Activity indicators
Show that Claude is thinking/working:
- "thinking..." when Claude is processing
- Throbber/typing indicator
- Words like "Hmm", "Let me think"

### Compacting indicator
Show context compacting progress:
- Detect compacting from tmux capture-pane
- Show progress in Telegram

### Tool results formatting
Beautiful tool results formatting:
- Syntax highlighting for code
- Collapsible for long outputs
- File previews

### Hidden tools filtering
Don't show tools not in CLI interface:
- TodoWrite
- Other internal tools
- Need to research which are hidden

### /settings command enhancements
Display current Claude session state:
- Current approval mode (accept edits, allow all, etc.)
- Number of background tasks
- Parse status bar from tmux capture-pane
- Format: "Mode: Accept edits | Background: 3 tasks"
- **Hardware stats** — CPU/RAM usage graph

### Thread create UX
Improve `/thread_create`:
- Without argument → show buttons with name options (magic names)
- Or input field "Enter name"
- Remove need to enter name on same line

### /shift_tab command
Command to toggle approval mode:
- Sends Shift+Tab to tmux
- Reports mode change: "Allow once → Allow for session"
- Parses current selection from tmux capture-pane

### Reply support
When replying to message, send context to tmux:
- Quote piece of message being replied to
- Format: `> quote\n\nresponse text`

### Images and files support
Support sending images and files from admin:
- Save to temp/project folder
- Send file path to tmux
- Possibly: inline images via base64

### Self-hosting: default chat = bot project
Default private chat with bot linked to codogram folder:
- Allows managing bot through itself
- No need to create separate group for bot development

### Forward unhandled commands
`/commands` without handler forward to Claude as-is:
- Currently added to tmux with double slashes, not sent
- Need fallback in `on_message` or separate handler

### Tool progress display
Show tool execution progress:
- Extend Task 5 in permission-detection plan
- Currently `ToolProgress` is parsed but not displayed (pass)
- **Insight:** In Claude first line is static (Task/Tool name), rest scrolls
  ```
  Task(Implement Task 1: Screen Parser)
    ⎿  Read 46 lines
       Read 30 lines
       Waiting…
  ```
- First line from jsonl can be used as anchor

### Ultrathink mode
`/ultrathink_mode` toggle, adds " ultrathink" to each message:
- Store in per-project settings
- Show status on /start

### Context window indicator
Show remaining space until compact:
- Parse from jsonl (if available) or tmux screen
- Show in /settings and/or status line

### Ctrl+B command
`/ctrl_b` sends Ctrl+B to tmux:
- Useful for vim-mode or tmux prefix

### Silent push notifications
Silent pushes for regular messages, loud for permissions and stops:
- Regular messages: `disable_notification=True`
- Permissions, generation stopped: loud push
- May need webhooks for fast reaction

### Silent mode
Mode without showing tool calls, only final generations:
- `/silent` command to toggle
- Filter TOOL_USE, TOOL_RESULT, show only TEXT

### Thread summarization
Summarize long threads (questionable):
- `/summary` command or automatic at N messages
- Use Claude API for summarization
- Question: is this needed if Telegram has scroll?

### Fix bullet point rendering
Replace large dot `•` with dot in code block:
- `•` renders poorly in some clients
- Replace with `` `•` `` or another symbol

## PoC / Research

### codogram-tmux-only
Experiment: use only tmux capture-pane without jsonl.
- See `docs/designs/2025-12-23-telegram-bridge-tmux-only.md`
- Pros: simpler, doesn't depend on Claude's internal format
- Cons: ANSI parsing, unstable
