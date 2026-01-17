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

### Menu redesign
Reorganized bot commands for better usability:
- Unified `/finish` for both worktree and regular topics
- Short aliases: `/thread`, `/branch`
- Deprecated commands redirect: `/thread_delete` → "Use /finish"
- Archive topics instead of delete (close + icon)
- See [docs/designs/done/2025-01-03-menu-redesign.md](designs/done/2025-01-03-menu-redesign.md)

### Session resume
Resume Claude session after crash or archived topic restore:
- Store session_id in ThreadInfo
- On /start in archived topic: `claude --resume <session_id>`
- Preserves conversation context instead of starting fresh
- Worktrees preserved after /finish for easy resume
- See [docs/designs/done/2026-01-05-session-resume.md](designs/done/2026-01-05-session-resume.md)

### E2E test structure
Manual E2E tests executed by Claude via Telegram MCP:
- Test suites: smoke (~2 min), critical (~15 min), full (~30 min)
- Tests organized by command: start, sessions, threads, branches, finish, permissions, watcher
- MCP tools for sending commands, reading responses, clicking buttons
- Bug documentation workflow with `docs/bugs/active/` reports
- See [docs/designs/done/2026-01-06-e2e-test-structure.md](designs/done/2026-01-06-e2e-test-structure.md)

### Worktree-safe config
Config moved to `~/.codogram/` to avoid worktree issues:
- `pip install -e` from worktree no longer breaks main bot
- New `dev-run.sh` for testing from worktrees (uses PYTHONPATH)
- `restart.sh` protection against running from worktree
- See [docs/designs/done/2026-01-07-worktree-safe-config.md](designs/done/2026-01-07-worktree-safe-config.md)

### Group → Supergroup migration
Handle chat_id change when topics are enabled in existing group:
- Telegram changes chat_id when converting group to supergroup (forum)
- Listen for `message.migrate_to_chat_id` event
- Auto-update chat_id in config when migration detected
- Scope-based menu: basic for groups, extended (/branch, /finish) for forums
- Menu registered on bot startup and on /start
- See [docs/designs/done/2026-01-07-group-to-supergroup-migration.md](designs/done/2026-01-07-group-to-supergroup-migration.md)

### MCP trust prompt support
Detect and display MCP server trust prompts:
- Box-style UI parsing with `╭╮╯╰│` characters
- `PromptType` enum for extensible prompt classification
- MCP prompts shown in Telegram with same buttons as regular prompts
- Auto-accept bypassed for MCP prompts (security)
- See [docs/designs/done/2026-01-07-mcp-trust-prompt.md](designs/done/2026-01-07-mcp-trust-prompt.md)

### Atomic permission message batches
Fix permission messages interleaving with launch_animation:
- Add `reply_markup` field to `OutgoingBatch` (applied to last message)
- Permission poller sends body + options + keyboard in single atomic enqueue
- Prevents other messages from appearing between permission parts
- See [docs/bugs/fixed/2026-01-12-permission-messages-interleaving.md](bugs/fixed/2026-01-12-permission-messages-interleaving.md)

### Thread/Branch create UX
Improved `/thread` and `/branch` name input:
- Without argument → show prompt "Thread/Branch name?" with buttons
- [🔮 Magic name] button generates random name (arcane, mystic...)
- User can type custom name as text message
- [<<] Go back cancels the flow
- With argument → validates and creates directly (unchanged)
- Flow state cleared on any new command
- See [docs/designs/done/2026-01-07-thread-branch-create-ux.md](designs/done/2026-01-07-thread-branch-create-ux.md)

### Session state display & control
Display and control Claude session state:
- **/shift_tab command** — send Shift+Tab to tmux, cycle approval mode
- **/settings enhancements** — show approval mode, background tasks, context usage
- **Status bar parsing** — parse line below input box (idle only)
- **Permission cancel on send** — cancel active permission before sending message
- See [docs/designs/done/2026-01-07-session-state-display.md](designs/done/2026-01-07-session-state-display.md)

### Stale worktree recovery
Handle deleted worktrees gracefully instead of crashing:
- `/resume`, `/start` — detect stale worktree_path, offer: recreate / resume in main / cancel
- `/finish` — warning + archive topic without git cleanup
- `/branch` — fallback to main as base branch
- "Resume in main" archives topic (feature work is done)
- See [docs/designs/done/2026-01-12-stale-worktree-recovery.md](designs/done/2026-01-12-stale-worktree-recovery.md)

### Fix gh repo create initial commit
`gh repo create --push` was failing on empty repo with "no commits found".
- Added `git commit --allow-empty -m "Initial commit"` before `gh repo create --push`

## Backlog

### Role model & chat registration
Minimal permission system for multi-user access:
- `/register_chat` — allow everyone in chat to message the bot (not just admins)
- Admin-only settings commands
- Roles: admin (full control) vs user (can send messages)
- Per-chat configuration

### Interface simplification settings
Admin commands to enable/disable features:
- Toggle `/thread` command visibility
- Toggle `/branch` command visibility
- Simplify menu for non-power-users
- Store in per-project settings

### Images and files input
Support sending images and files from admin to Claude:
- Save to temp/project folder
- Send file path to tmux
- Possibly: inline images via base64

### Telegram safety context
Inject safety guidelines when starting thread/branch/project:
- Tell Claude what's safe to do in Telegram environment
- Warn about dangerous operations (don't kill tmux, etc.)
- Project-specific constraints
- Need to design the exact guidelines

### Protected environment for non-devs
Allow product managers to use Claude without breaking environment:
- Rollback mechanism after session
- Or sandboxed/isolated execution
- Easy recovery if something breaks
- Need R&D on best approach

### Inline suggests on Claude messages
Suggestion buttons attached to Claude's responses:
- Click to send suggested action/response
- Context-aware based on message content
- Quick follow-up actions

### Simplified output & hidden tools
Cleaner output by default:
- Don't dump full permission text on auto-accept
- Hide tool calls by default (TodoWrite, Read, etc.)
- `/silent` command to toggle tools visibility
- Filter TOOL_USE, TOOL_RESULT, show only TEXT
- High priority — improves daily UX significantly

### Activity indicators
Show that Claude is thinking/working:
- Generation indicator appears ABOVE input box in tmux
- Format: `· Hatching… (esc to interrupt · 42s · ↓ 0 tokens)`
- Random verbs: "Hatching", "Enchanting", "Conjuring", etc.
- Parse from tmux capture-pane
- Show typing indicator or status in Telegram

### Message queue until session ready
Cache user messages while session is binding, send when ready:
- After `/start` or `/branch`, session binding takes ~1-2 minutes
- During this window messages go to tmux but responses don't appear
- Solution: queue messages while `awaiting_new_session=True`
- Send all queued messages when session binds
- Show "⏳ Connecting..." feedback to user
- See bug: [2026-01-07-session-not-immediately-active.md](bugs/active/2026-01-07-session-not-immediately-active.md)

### Tool visibility R&D
Research and implement tool display improvements:
- **Tool progress display** — show execution progress (currently parsed but not shown)
- **Hidden tools filtering** — don't show TodoWrite and other internal tools
- **Insight:** In Claude first line is static (Task/Tool name), rest scrolls:
  ```
  Task(Implement Task 1: Screen Parser)
    ⎿  Read 46 lines
       Read 30 lines
       Waiting…
  ```
- First line from jsonl can be used as anchor
- Need to research which tools are hidden in CLI

### Claude error detection
Detect when Claude Code exits with error (API errors, network issues, etc.):
- Research how errors are displayed in tmux (API error, connection issues)
- Parse tmux capture-pane for error patterns
- Send error text to user: "⚠️ Claude error: <error text>. Figure it out and /start"
- Detect shell prompt appearing after Claude was active

### Reply support
When replying to message, send context to tmux:
- Quote piece of message being replied to
- Format: `> quote\n\nresponse text`

### Migrate strings to strings.py
Move all hardcoded strings to `src/codogram/strings.py`:
- handlers/*.py — command responses
- launch_animation.py — startup statuses
- history_watcher.py — notifications
- keyboards.py — buttons
- services/start_flow.py — wizard buttons
- See `docs/specs/tone-of-voice.md` for guidelines

---

### Manual topic registration
When `/start` is called in a manually created topic:
- If resume possible (archived topic with session_id) → resume without questions
- Otherwise show menu: "Create thread" / "Create worktree"
- Allows using standard Telegram UI for topic creation

### Queue reliability improvements
Improve TelegramQueue resilience:
- **Retry on network errors** — `ServerDisconnectedError` currently not retried, message lost
- **1 rps rate limiting** — proactive throttling to avoid hitting Telegram limits
- **Exponential backoff** — for rate limit retries

### Claude exit detection
Detect when Claude exits normally (not crash):
- Show `[~] Claude exited. Use /start to restart.` notification
- Detect shell prompt after Claude UI disappears
- Must track `claude_was_active` to avoid false positives on startup
- Must distinguish shell prompt `❯` from Claude selector `❯ 1. Yes`
- See reverted attempt: 8b6baf8 (had issues with false positives)

### Cleanup command
Explicit deletion of archived branches when disk space or git cleanup needed:
- `/cleanup` — list archived branches with inactivity days
- `/cleanup <branch>` — delete specific branch
- Deletes worktree and git branch, preserves session jsonl
- See [docs/designs/2026-01-05-cleanup-command.md](designs/2026-01-05-cleanup-command.md)

### GitHub Actions CI
- Workflow for running tests on PR
- pytest + type checking

### Voice → Whisper
Voice messages via Whisper transcription:
- Use existing code from bz-merch-assistant
- `ai_bot_core/services/whisper.py`

### Pin startup message
Pin message on session start:
- `Claude started in claude-codogram-sublime`
- `Connect: tmux attach -t claude-codogram-sublime`
- Unpin previous on restart

### Hardware stats
Display CPU/RAM usage:
- Graph or text indicator in /settings
- Monitor Claude process resource consumption

### Compacting indicator
Show context compacting progress:
- Detect compacting from tmux capture-pane
- Show progress in Telegram

### Tool results formatting
Beautiful tool results formatting:
- Syntax highlighting for code
- Collapsible for long outputs
- File previews

### Self-hosting: default chat = bot project
Default private chat with bot linked to codogram folder:
- Allows managing bot through itself
- No need to create separate group for bot development

### Forward unhandled commands
`/commands` without handler forward to Claude as-is:
- Currently added to tmux with double slashes, not sent
- Need fallback in `on_message` or separate handler

### Ultrathink mode
`/ultrathink_mode` toggle, adds " ultrathink" to each message:
- Store in per-project settings
- Show status on /start

### Background process command
`/ctrl_b` sends Ctrl+B twice to background running processes:
- Sequence: Ctrl+B → sleep(0.1) → Ctrl+B
- Useful when Claude spawns long-running tasks

### Silent push notifications
Silent pushes for regular messages, loud for permissions and stops:
- Regular messages: `disable_notification=True`
- Permissions, generation stopped: loud push
- May need webhooks for fast reaction

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
