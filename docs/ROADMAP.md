# Codogram Roadmap

[Русская версия](ROADMAP.ru.md)

## Done

### Inline auto-accept notification
Show auto-accept as edit to previous tool message instead of new message:
- Edit last tool message to add "🤖 auto accepted" suffix
- Reduces chat noise, provides better context
- Hint every 10th: `/auto_accept to disable`
- See [docs/designs/done/2025-01-29-inline-auto-accept-design.md](designs/done/2025-01-29-inline-auto-accept-design.md)

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

### AskUserQuestion support
Full support for Claude's AskUserQuestion tool prompts:
- Parse question text and options from tmux screen
- Single-select: tap button → send number to tmux
- Multi-select: toggle checkboxes in Telegram, send diff on Submit
- "Type something" option detection with special "✏️ Type your answer" message
- Question progress header: "☐ Title (N/M)" for multi-question flows
- Auto-delete messages when user sends text or /esc (like permission poller)
- Refactored with dataclasses and helper functions
- See [docs/designs/done/2026-01-21-askuserquestion-support.md](designs/done/2026-01-21-askuserquestion-support.md)

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
- `stop-and-restart.sh` protection against running from worktree
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

### Status messages unification
All user-facing messages centralized in `strings.py`:
- 170 constants for all status messages, prompts, errors, button texts
- `STATUS_*` prefixes (`[v]`, `[x]`, `[!]`, `[~]`, `[?]`, `[i]`)
- Send vs edit pattern: first edit removes buttons, subsequent statuses via send
- Consistent tone-of-voice across all handlers
- See [docs/designs/done/2026-01-17-status-messages-unification.md](designs/done/2026-01-17-status-messages-unification.md)

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

### Images and files input
Send images and files from Telegram to Claude:
- Photos saved to `tmp/input-files/{thread}/` with timestamped names
- Documents (PDF, txt, md, etc.) supported with extension whitelist
- Format: `See file: ./path/to/file` for Claude to read
- Video files rejected (audio/voice handled by Whisper transcription)
- Path traversal protection and 20MB size limit
- See [docs/designs/done/2026-01-17-image-file-input.md](designs/done/2026-01-17-image-file-input.md)

### Verbose mode & settings improvements
Per-thread/per-project verbose output toggle and /settings UX:
- `/verbose` — toggle verbose output on/off (● on / ○ off indicators)
- `/settings` inline buttons for quick toggles (/auto_accept, /verbose, /shift_tab, close)
- Short hash IDs in callback data (fix for long tmux session names)
- Mode display with emojis: ⏵⏵ accept edits, ⏸ plan mode, default
- Hint text "(use /shift_tab to cycle)" in settings
- Close button deletes settings message
- See [docs/plans/done/2026-01-17-verbose-toggle-plan.md](plans/done/2026-01-17-verbose-toggle-plan.md)

### DM onboarding
Interactive onboarding in direct messages with bot:
- Welcome carousel with bot features overview
- Environment validation (BASE_DIR, tmux, claude, git, gh, whisper)
- Critical checks block progress, optional checks show warnings
- `/check_env` command to rerun validation anytime
- `/dashboard` shows all projects with active sessions count
- `/intro` to replay onboarding
- Push notification when bot is added to a group
- DM-specific command menu
- See [docs/designs/done/2025-01-18-dm-onboarding.md](designs/done/2025-01-18-dm-onboarding.md)

### Group authorization
Allow bot usage in groups where at least one group admin is in ADMIN_IDS:
- Private chat: only ADMIN_IDS users allowed
- Group with admin from ADMIN_IDS: any group member can use bot
- Group without admin from ADMIN_IDS: blocked
- Event-driven: bot added/removed events, admin left/demoted events
- Persistence: allowed_groups stored in config.json
- Re-validation after bot restart
- Regular groups: skip admin rights check (topics not supported)
- Supergroups: check admin rights for topics/rename features
- See [docs/plans/done/2026-01-18-group-authorization-design.md](plans/done/2026-01-18-group-authorization-design.md)

### Project restructure
Reorganized codebase into logical modules:
- `telegram/` — queue, adapters, keyboards, launch animation
- `tmux/` — sessions, commands, window creation
- `claude/` — screen parsing, permission prompts, history.jsonl
- `git/` — worktree, branches, utils
- `core/` — project state, background task coordinator
- See [docs/designs/done/2026-01-21-project-restructure.md](designs/done/2026-01-21-project-restructure.md)

### Thread/branch command merge and menu simplification
Unified commands instead of separate thread/branch/finish:
- `/new_chat` — create new chat (thread or branch with worktree)
- `/finish_chat` — finish chat (archive topic)
- `/clear_context` — reset Claude context (new session)
- `/hard_reset` — full project reset
- Intuitive names without technical terminology
- Context-aware behavior: from main → thread, from branch → nested branch
- Relative paths in UI (`./project` instead of full path)
- See [docs/designs/done/2026-01-19-command-merge-design.md](designs/done/2026-01-19-command-merge-design.md)

### Avatar emoji pack
Custom emoji pack from group members' avatars:
- `/exp_avatar_pack` — toggle on/off, create or delete pack
- Create pack on group → supergroup migration (async)
- Add avatar when member joins, remove when leaves
- Generate placeholder (letter + color) for users without avatar
- Fun random names: "Cosmic Dolphins", "Epic Titans", etc.
- Topic launch hint with pack link when feature enabled
- Limitation: Premium required to set custom emoji as topic icon
- See [docs/designs/done/2026-01-18-emoji-pack-design.md](designs/done/2026-01-18-emoji-pack-design.md)

### Set up flow redesign + robust start
Full redesign of /start flow with robust error handling and intuitive setup UX:
- Three setup paths: Clone repository, Connect existing folder, New project
- SetupFlow FSM with states for each step
- SetupBlockerMiddleware blocks non-setup commands during flow
- Cancel button and /reset_all to abort setup
- Proper navigation with Go back buttons
- See [docs/designs/done/2026-01-18-start-flow-v2.md](designs/done/2026-01-18-start-flow-v2.md)

### Message response mode
Per-chat setting for when bot should respond:
- **All messages** — respond to everything (default)
- **Polite** — skip messages with @mentions to others
- **Mentions only** — respond only when bot is @mentioned or replied to
- Toggle via `/response_mode` or `/settings` button

### Voice → Whisper transcription
Voice messages and audio files transcribed via OpenAI Whisper:
- Voice messages (.ogg), audio files (.mp3, etc.), and video notes (круглые видео)
- "Transcribing..." status, then "«text» → Claude" on success
- Friendly error messages for API errors (too large, timeout, no speech, etc.)
- Configurable via OPENAI_API_KEY, OPENAI_BASE_URL, WHISPER_TIMEOUT
- `/whisper_stats` in DM — usage reports by users/projects with period filters (7d/30d/all)
- Usage logging to `~/.codogram/whisper-usage.jsonl` for cost tracking
- See [docs/designs/done/2026-01-18-whisper-transcription-design.md](designs/done/2026-01-18-whisper-transcription-design.md)

### Verbose mode detailed menu
Granular control over bot output via `/verbose` submenu:
- `[full]` — show everything (tool calls, auto-accept notifications)
- `[-5 strings] [+5 strings]` — adjust line limit
- `[just headers]` — tool names only, no content
- `[only current header]` — single updating message with latest tool
- `[total silence]` — only final user-facing messages

### Toggle bullet point (•)
Separate setting to enable/disable bullet point `•` prefix on bot messages.

### Hide/show thinking
Per-chat toggle for `<thinking>` block visibility:
- Hidden by default for cleaner output
- Enable for debugging or learning

### Collapsible permission prompts
Permission prompts show only header by default:
- Action type shown (Bash, Read, Edit, etc.)
- `[Show more]` button expands full context
- Message edits in place to reveal details

### Sidechain agent text capture
Fix missing Claude responses due to Claude Code sidechain behavior:
- Claude Code sometimes writes text to `aprompt_suggestion` sidechain agents instead of main jsonl
- Main jsonl only gets `thinking` block with `stop_reason: null`
- Text visible on screen but not in main jsonl
- Fix: JsonlWatcher now also checks `subagents/` folder for new `agent-aprompt_suggestion-*.jsonl` files
- Extracts text from line 1 and yields as TEXT entry
- Related: anthropics/claude-code#13326, anthropics/claude-code#20660

### Settings in DM / Global defaults
Manage global default settings from DM with the bot:
- `/settings` in DM — view and toggle global defaults
- All settings commands work in DM (auto_accept, response_mode, verbose_mode, etc.)
- `/reset_to_default` — reset thread/project settings to inherit from global defaults
- Two-level inheritance: Thread → Global defaults → Hardcoded defaults
- `feat_avatar_pack` is per-project (not per-thread) with global default override
- See [docs/designs/done/2026-01-27-settings-in-dm-design.md](designs/done/2026-01-27-settings-in-dm-design.md)

## Beta Test

### Compacting detection
Detect when Claude compacts conversation and notify user:
- Parse thinking status for "Compacting" keyword
- One-time notification `[i] Claude is compacting conversation...`
- Enabled for all, still debugging

### Activity indicators
Show that Claude is thinking/working:
- Generation indicator appears ABOVE input box in tmux
- Parse from tmux capture-pane
- Show thinking status in Telegram
- Toggle: `/exp_thinking_status`

### Input suggestions
Show Claude's suggested input in Telegram:
- Parse suggestion from input box (text with `↵ send` marker)
- Display as ReplyKeyboard for one-tap send
- Toggle: `/exp_suggestions`

### Stuck message recovery
Auto-detect and resend messages stuck in Claude's input:
- Detect `[Pasted X lines]` or last sent message stuck in input field
- Debounce: send Enter only after seeing same stuck text twice
- Prevents messages from getting lost due to race conditions
- See [docs/designs/done/2026-01-17-stuck-message-recovery.md](designs/done/2026-01-17-stuck-message-recovery.md)

## In Progress

### Auto-suspend & auto-resume
Save RAM by killing idle sessions, auto-resume on user message:
- **Auto-suspend:** Kill tmux after 12h inactivity (silent, no notification)
- **Auto-resume:** Relaunch Claude when user writes to dead session:
  - Suspended session → "Session was suspended. Resuming..."
  - Tmux missing → "Tmux not found. Launching..."
  - Claude crashed → "Claude not responding. Relaunching..."
- Track activity via `last_activity_at` + jsonl mtime
- Hold user message during resume, send after Claude ready
- See [docs/plans/2026-01-24-auto-suspend-design.md](plans/2026-01-24-auto-suspend-design.md)

### Architecture review and clean up
Ongoing architecture improvements and technical debt reduction.
- Phase 1: project restructure ✅
- Phase 2: permission poller refactoring ✅
- See [docs/plans/2026-01-22-architecture-refactoring-roadmap.md](plans/2026-01-22-architecture-refactoring-roadmap.md) for full backlog

### Global settings in DM
`/settings` command in DM with bot to set defaults for all projects:
- Default verbose mode, response mode, auto-accept, etc.
- New chats/threads inherit these defaults
- Per-chat settings override global defaults
- Configure once — works everywhere

## Active Bugs (External)

### Claude Code: --resume ignores conversation context
Resume command uses correct session ID but Claude says "this is the beginning of our conversation":
- `claude --resume <session_id>` executes successfully
- Session file exists with full history (675 lines)
- sessions-index.json has correct entry
- But model doesn't receive conversation context
- Related: anthropics/claude-code#15837, #3138, #10161
- **Status:** Waiting for Claude Code fix, no workaround found

### Claude Code: sessions-index.json randomly empties
Session index file becomes empty, breaking resume picker:
- Caught on cook-guy and multiple other projects
- jsonl files exist but sessions-index.json has `"entries": []`
- Claude Code v2.1.23
- Root cause unknown — not Codogram's fault (we don't touch this file)
- Workaround: manually restore index entry from jsonl data
- Related: anthropics/claude-code#18311

## Backlog

### Manual group approval tracking
Track manually approved groups separately from auto-approved:
- Store approving admin ID per group
- Invalidate only if approving admin leaves the group (not if they lose admin role)
- 24h grace period when approver leaves, with notification
- Monthly review reminders with [Keep]/[Revoke] buttons
- `/allowed_groups` command to view and revoke manual approvals
- See [docs/designs/2026-01-28-manual-group-approvals.md](designs/2026-01-28-manual-group-approvals.md)

### Secure key-value storage
Encrypted storage for sensitive data (API keys, tokens, secrets):
- Claude can store and retrieve secrets without exposing them in chat
- Encrypted at rest
- Per-project or global scope
- Commands or MCP tool for access

### Claude file sending
Allow Claude to send files to Telegram:
- Send generated files (code, images, documents) directly to chat
- MCP tool or special output format
- Useful for exports, reports, generated assets

### Fork command
`/fork` command to create a copy of current branch:
- Fork current worktree to new branch
- Useful when conversation goes in wrong direction
- Preserve context but start fresh direction

### Companion / personal account integration
Connect a Telegram user account to the bot:
- **Service account** — read chat history, join groups, bypass bot limitations
- **Personal account** — receive your messages, reply with Claude's help from your own account
- MTProto client (Telethon) alongside Bot API
- Research needed: auth flow, session storage, bot↔userbot architecture

### Voice messages from bot
Text-to-speech for Claude's responses:
- Convert Claude's text responses to voice messages
- OpenAI TTS or similar API
- Toggle per-chat or per-message
- Useful for listening while multitasking

### Project-less chat mode
Connect bot to chat without creating a project:
- Starter worktrees in codogram folder
- Quick access without full project setup
- Option to "promote" to real project later
- Useful for quick questions or experiments

### Pass user names in multi-user chats
When multiple people use same chat, identify who's talking:
- Inject sender name before message: `[Username]: message`
- Helps Claude understand conversation context
- Toggle setting per chat

### Team mode: user avatar and name for topics
In team mode, personalize topics with user identity:
- Topic icon = user's avatar (from emoji pack)
- Topic name includes user's name
- Easy to see who's working on what branch
- Requires avatar emoji pack feature

### Chat context for response modes
Pass recent chat messages to Claude in polite/mention modes:
- Save last N messages from chat
- Inject context when bot responds to mention/reply
- Helps Claude understand conversation flow

### Chat context exploration tool
MCP tool for Claude to read Telegram chat history:
- Query recent messages from current chat
- Search by user, date, keywords
- Useful for assistant-style interactions

### Tool spam reduction
Reduce noise from internal tool calls in assistant mode:
- Hide TodoWrite, Read, Glob etc. from output
- Show only user-relevant results
- Related: Hidden tool calls (silent mode)
- May need architecture changes for comfortable assistant UX

### Persistent setup state
Save FSM state to config file to survive bot restarts:
- Save state and data on each `state.set_state()` / `state.update_data()`
- Restore FSM state from config on bot startup
- Clear saved state when setup completes
- Prevents "restart during setup = start over" problem

### Reply support
When replying to message, send context to tmux:
- Quote piece of message being replied to
- Format: `> quote\n\nresponse text`

### Tables and diagrams rendering
Render tables and diagrams from text to images:
- Convert ASCII/markdown tables to images
- Convert mermaid/plantuml diagrams to images
- Better readability in Telegram

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

### Message queue until session ready
Cache user messages while session is binding, send when ready:
- After `/start` or `/branch`, session binding takes ~1-2 minutes
- During this window messages go to tmux but responses don't appear
- Solution: queue messages while `awaiting_new_session=True`
- Send all queued messages when session binds
- Show "⏳ Connecting..." feedback to user
- See bug: [2026-01-07-session-not-immediately-active.md](bugs/active/2026-01-07-session-not-immediately-active.md)

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

### Hardware stats
Display CPU/RAM usage:
- Graph or text indicator in /settings
- Monitor Claude process resource consumption


### Tool results formatting
Beautiful tool results formatting:
- Syntax highlighting for code
- Collapsible for long outputs
- File previews

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

### Attach to existing Claude session
Connect Telegram to a Claude session started from terminal:
- User starts `claude` in tmux on laptop
- Sends `/connect` or `/attach` in Telegram
- Bot discovers existing tmux sessions with Claude
- Shows list to pick from (or auto-connect if only one)
- Starts monitoring the session for prompts/tool calls

### codogram-tmux-only
Experiment: use only tmux capture-pane without jsonl.
- See `docs/designs/2025-12-23-telegram-bridge-tmux-only.md`
- Pros: simpler, doesn't depend on Claude's internal format
- Cons: ANSI parsing, unstable

### Ollama launch
Run Claude Code CLI with other models via Ollama:
- Launch codogram with local LLMs instead of Claude API
- Useful for testing, development, or cost savings
- Research: how Claude Code handles different model backends
