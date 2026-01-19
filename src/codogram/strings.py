"""All user-facing strings in one place.

See docs/specs/tone-of-voice.md for guidelines.
"""

# Status prefixes (always in backticks for markdown)
STATUS_OK = "`[v]`"
STATUS_ERR = "`[x]`"
STATUS_WARN = "`[!]`"
STATUS_PENDING = "`[~]`"
STATUS_QUESTION = "`[?]`"
STATUS_INFO = "`[i]`"

# Toggle states
STATUS_ON = "`● on`"
STATUS_OFF = "`○ off`"

# Truncation marker (ASCII scissors)
SNIP = "[--- 8< ---]"


# --- Launch animation ---

LAUNCH_CREATING_TMUX = f"{STATUS_PENDING} Creating tmux session..."
LAUNCH_STARTING = f"{STATUS_PENDING} Starting Claude..."
LAUNCH_RESUMING = f"{STATUS_PENDING} Resuming session..."
LAUNCH_WAITING = f"{STATUS_PENDING} Waiting for Claude..."
LAUNCH_TIMEOUT = f"{STATUS_ERR} Timeout: Claude didn't start in 2 minutes"
LAUNCH_ERROR = f"{STATUS_ERR} Launch error: {{error}}"
LAUNCH_READY = f"{STATUS_OK} Claude ready"
LAUNCH_READY_WITH_ATTACH = f"{STATUS_OK} Claude ready\n\nTo see Claude UI: `tmux attach -t {{tmux_name}}`"
LAUNCH_PROJECT_CWD_NOT_SET = f"{STATUS_ERR} Project cwd not set. Re-register with /start"

# Launch service (worktree creation)
LAUNCH_CREATING_BRANCH = f"{STATUS_PENDING} Creating branch `{{branch}}` from `{{base}}`..."
LAUNCH_BRANCH_ERROR = f"{STATUS_ERR} {{error}}"
LAUNCH_WORKTREE_CREATED = f"{STATUS_OK} Worktree: `{{path}}`"


# --- Session management ---

SESSION_BOUND = f"{STATUS_OK} New session bound"
SESSION_CLOSED = f"{STATUS_WARN} Claude session closed: {{name}}"
SESSION_NOT_FOUND = f"{STATUS_WARN} Session not found. Try /start"
SESSION_EXPIRED = "Session expired"
SESSION_EXPIRED_START = "Session expired, start again with /start"
SESSION_STOPPED = "Session stopped. Use /start to launch"
SESSION_RESTART_CONFIRM = "Restart session `{tmux_name}`?"

NEW_SESSION = f"{STATUS_PENDING} Creating new session..."
CLEAR_SESSION = f"{STATUS_PENDING} Clearing session..."

CLAUDE_CRASHED = f"{STATUS_WARN} Claude crashed: {{reason}}\nUse /restart to restart"
CLAUDE_AUTO_RESTARTED = f"{STATUS_INFO} Claude exited, auto\\-restarting\\.\\.\\."

COMPACTING_STARTED = f"{STATUS_INFO} Claude is compacting conversation\\.\\.\\."


# --- Project/Thread ---

PROJECT_NOT_FOUND = "Project not found"
PROJECT_NOT_REGISTERED = "Project not registered. Use /start"
PROJECT_NAME_INVALID = "Project name can only contain letters, digits, `-` and `_`"
PROJECT_NAME_PROMPT = "Send project name (e.g. `my-project`):"

THREAD_NOT_FOUND = "Thread not found"
THREAD_NOT_FOUND_START = "Thread not found. Use /start"
THREAD_CLOSED = "Thread closed"
THREAD_EXISTS = "Thread with name '{name}' already exists"
THREAD_NAME_INVALID = "Name can only contain letters, digits, - and _"
THREAD_CLOSE_CONFIRM = "Close thread '{name}'?\nTopic and tmux session will be deleted"
THREAD_NOT_LINKED = "This topic is not linked to a Claude session"
THREAD_TOPIC_ONLY = "This command can only be used in a topic"
THREAD_CONNECT_HINT = "Use /start to connect Claude"

THREAD_CREATING = f"{STATUS_PENDING} Creating thread `{{name}}`..."
THREAD_CREATED = f"{STATUS_OK} Thread `{{name}}` created"


# --- Directory/Git ---

DIR_NOT_FOUND = "Directory `{path}` not found.\n\nWhat to do?"
DIR_NOT_EXISTS = "Directory `{path}` does not exist"
DIR_CREATED = "Directory `{path}` created"
DIR_ERROR = "Error creating directory: {error}"

GIT_SETUP_PROMPT = """{dir_created}

**Setup git?**

• `git init` — local repository
• `git init + gh repo create` — create on GitHub
• `git clone` — clone existing
• No git — empty folder"""

GIT_INIT_OK = "Git initialized. Launching Claude..."
GIT_INIT_ERROR = "Error git init: {error}"
GIT_VISIBILITY = "Repository visibility?"
GIT_REPO_CREATING = "Creating GitHub repository..."
GIT_REPO_CREATED = "Repository created. Launching Claude..."
GIT_CLONE_PROMPT = """Send repository URL:
• SSH: `git@github.com:user/repo.git`
• HTTPS: `https://github.com/user/repo.git`"""
GIT_CLONE_PROGRESS = "Cloning repository..."
GIT_CLONE_ERROR = "Clone error: {error}"
GIT_ERROR = "Error: {error}"

DIR_PATH_PROMPT = "Send project directory path:"


# --- Claude status ---

CLAUDE_ACTIVE = "Claude active in `{tmux_name}`"
CLAUDE_ATTACH = "To see Claude UI: `tmux attach -t {tmux_name}`"
CLAUDE_NOT_RUNNING = f"{STATUS_INFO} Claude not running in `{{cwd}}`\\.\n\nUse /start to launch\\."
CLAUDE_CONNECTED = "Connected to tmux: `{tmux_session}`"
CLAUDE_NO_SESSION = "No active Claude session. Use /start to launch"
CLAUDE_TMUX_NOT_FOUND = "tmux session not found. Start Claude in terminal"
CLAUDE_NO_RESTART = "No active session to restart"


# --- URL Validation ---

GIT_URL_INVALID_WIKI = f"{STATUS_ERR} This is a wiki page, not a repository"
GIT_URL_INVALID_BLOB = f"{STATUS_ERR} This is a file link. Use repository URL"
GIT_URL_INVALID_GIST = f"{STATUS_ERR} Gists cannot be cloned as projects"
GIT_URL_INVALID_FORMAT = f"{STATUS_ERR} Invalid URL. Use https:// or git@ format"
GIT_URL_RETRY_PROMPT = "Send valid repository URL:"


# --- Project State ---

PROJECT_NOT_READY = f"{STATUS_WARN} Project not ready. Use /start first"
CLAUDE_STARTING = f"{STATUS_WARN} Claude is starting... wait a moment"


# --- Clone Progress ---

CLONE_IN_PROGRESS = f"{STATUS_PENDING} Cloning repository... may take several minutes for large repos"


# --- Reset Flow ---

RESET_FLOW_IN_PROGRESS = f"{STATUS_WARN} Start flow in progress. Wait for completion or use /cancel"
RESET_CLEANUP_FAILED = f"{STATUS_WARN} Could not delete directory `{{path}}`\\n\\nDelete manually: `rm -rf {{path}}`"

RESET_NO_PROJECT = f"{STATUS_INFO} Nothing to reset. Use /start to begin."
RESET_COMPLETE = f"{STATUS_OK} Reset complete. Use /start to begin."
RESET_CONFIRM = f"""{STATUS_QUESTION} Reset project `{{name}}`?

This will disconnect Claude and clear settings."""
RESET_CONFIRM_TOPIC = f"""{STATUS_QUESTION} Reset entire project `{{name}}`?

This will disconnect Claude in all topics and clear settings."""
RESET_UNCOMMITTED = f"{STATUS_WARN} Uncommitted changes in `{{path}}`"
RESET_DIR_CHOICE = f"{STATUS_QUESTION} Delete directory `{{path}}`?"
RESET_DONE = f"""{STATUS_OK} Project reset

• Config cleared
• Claude stopped
• Directory {{dir_status}}

/start to begin new project"""


# --- Misc ---

TOPICS_REQUIRED_GROUP = f"{STATUS_WARN} This command requires a group with topics"
TOPICS_REQUIRED_ENABLE = f"""{STATUS_WARN} Topics required

To enable:
1. Open group settings \\(tap group name\\)
2. Edit \\(pencil icon\\)
3. Topics → Enable

_Requires admin rights_"""

CREATE_PROJECT_NOT_FOUND = f"{STATUS_WARN} Project not found"
CREATE_TOPIC_ERROR = f"{STATUS_ERR} Error creating topic"

LAUNCH_IN_PROGRESS = "Launch already in progress..."
CANCELLED = "Cancelled"
INVALID_CALLBACK = "Invalid callback"
TOPICS_REQUIRED = "This chat doesn't support topics. Enable Topics in group settings"
TOPIC_CREATE_ERROR = "Error creating topic: {error}"
TOPIC_DELETE_ERROR = "Error deleting topic: {error}"


# --- File input ---

FILE_VIDEO_NOT_SUPPORTED = f"{STATUS_WARN} Video files are not supported"
FILE_TYPE_NOT_SUPPORTED = "This file type is not supported"


# --- Audio/Whisper ---

AUDIO_TRANSCRIBING = f"{STATUS_PENDING} Transcribing..."
AUDIO_SENT = f"{STATUS_OK} «{{text}}» → Claude"

AUDIO_ERR_TOO_LARGE = f"{STATUS_ERR} Transcription failed: file too large"
AUDIO_ERR_FORMAT = f"{STATUS_ERR} Transcription failed: unsupported format"
AUDIO_ERR_TIMEOUT = f"{STATUS_ERR} Transcription failed: timeout, try again"
AUDIO_ERR_GENERIC = f"{STATUS_ERR} Transcription failed: {{error}}"
AUDIO_ERR_NO_SPEECH = f"{STATUS_ERR} No speech detected"
AUDIO_ERR_NOT_CONFIGURED = f"{STATUS_INFO} Voice messages? Nice! But admin needs to set OPENAI_API_KEY first"
FILE_TOO_LARGE = "File too large. Max 20MB"
FILE_DOWNLOAD_FAILED = "Download failed. Try again"


# --- Resume (deprecated) ---

RESUME_NOT_SUPPORTED_MULTI = f"{STATUS_WARN} /resume not supported in multi-session mode\nUse /thread_create for a new thread"
RESUME_NOT_SUPPORTED = f"{STATUS_WARN} /resume not supported\nUse /start to connect to existing session"


# --- Flavor Text (shown ~30% of time after success) ---

# Time of day
FLAVOR_EARLY_BIRD = "Early bird session starts…"
FLAVOR_LATE_NIGHT = "Late night session starts…"
FLAVOR_MIDNIGHT = "Midnight hacking begins…"
FLAVOR_WEEKEND = "Weekend warrior"

# Milestones
FLAVOR_SESSION_10 = "Session #10. Getting warmed up"
FLAVOR_SESSION_50 = "Session #50. Power user detected"
FLAVOR_SESSION_100 = "Century club unlocked"
FLAVOR_STREAK_7 = "Week streak continues…"
FLAVOR_STREAK_30 = "Month streak"

# Moments
FLAVOR_FIRST_TODAY = "First session today"
FLAVOR_LONG_TIME = "Long time no see"
FLAVOR_FRIDAY_EVENING = "Friday evening deploy"
FLAVOR_BUSY_DAY = "Busy day"

# Random
FLAVOR_RANDOM = [
    "Let's build something…",
    "Ready when you are",
    "Back to work",
]


# --- Buttons ---

BTN_YES_LAUNCH = "Yes, launch"
BTN_YES_CLOSE = "Yes, close"
BTN_YES_RESTART = "Yes, restart"
BTN_NO = "No"
BTN_CANCEL = "Cancel"
BTN_CANCEL_X = "[x] Cancel"
BTN_CREATE = "Create"
BTN_DIFFERENT_PATH = "Different path"
BTN_NO_GIT = "No git"
BTN_CONTINUE = "Continue"
BTN_KEEP_DIR = "Keep directory"
BTN_DELETE_DIR = "Delete"
BTN_DELETE_ANYWAY = "Delete anyway"
BTN_GO_BACK = "[<<] Go back"
BTN_MAGIC_NAME = "🔮 Magic name"
BTN_RECREATE_WORKTREE = "Recreate worktree"
BTN_CREATE_NEW = "Create new"
BTN_RESUME_IN_MAIN = "Resume in main"
BTN_CLOSE = "Close"


# --- Worktree Recovery ---

ERR_INVALID_CALLBACK = f"{STATUS_ERR} Invalid callback data"
ERR_PROJECT_NOT_FOUND = f"{STATUS_ERR} Project not found"
ERR_THREAD_NOT_FOUND = f"{STATUS_ERR} Thread not found"

WORKTREE_RECREATE_FAILED = f"""{STATUS_ERR} Failed to recreate worktree: {{path}}

What to do:
* /finish — archive this topic
* /thread — create new topic in main
* /branch — create new worktree branch"""

WORKTREE_BRANCH_CREATE_FAILED = f"""{STATUS_ERR} Failed to create branch: {{path}}

What to do:
* /finish — archive this topic
* /thread — create new topic in main
* /branch — create new worktree branch"""

WORKTREE_TOPIC_ARCHIVED = f"""{STATUS_OK} Topic archived

Use General or /thread for new session."""


# --- Finish/Archive ---

FINISH_NOTHING_IN_GENERAL = f"{STATUS_INFO} Nothing to finish in General. Use /clear to reset session"
FINISH_PROJECT_NOT_REGISTERED = f"{STATUS_WARN} Project not registered. Use /start first"
FINISH_THREAD_NOT_FOUND = f"{STATUS_WARN} Thread not found"

FINISH_ARCHIVE_CONFIRM = f"""{STATUS_QUESTION} Archive topic `{{name}}`?

This will close the topic and stop Claude session"""

FINISH_WORKTREE_NOT_FOUND = f"""{STATUS_WARN} Worktree not found: `{{path}}`

Archiving topic without git cleanup"""

FINISH_UNCOMMITTED_CHANGES = f"{STATUS_WARN} Branch `{{branch}}` has uncommitted changes"

FINISH_ARCHIVING = f"{STATUS_PENDING} Archiving `{{name}}`..."
FINISH_ARCHIVED = f"{STATUS_OK} Topic `{{name}}` archived"

FINISH_BRANCH_OPTIONS = """Finish branch `{name}`:

Base: `{base}`"""

FINISH_MERGE_CONFIRM = f"""{STATUS_QUESTION} Merge `{{branch}}` -> `{{target}}`?

Choose push option:"""

FINISH_MERGING = f"{STATUS_PENDING} Merging `{{branch}}` -> `{{target}}`..."
FINISH_MERGE_FAILED = f"""{STATUS_ERR} Merge failed: {{error}}

Resolve conflicts manually and try again."""

FINISH_PUSHING = f"{STATUS_PENDING} Pushing `{{target}}`..."
FINISH_PUSH_FAILED = f"""{STATUS_WARN} Merged but push failed: {{error}}

Push manually: `git push origin {{target}}`"""

FINISH_ARCHIVING_TOPIC = f"{STATUS_PENDING} Archiving topic..."
FINISH_CLEANING_WORKTREE = f"{STATUS_PENDING} Cleaning up worktree..."

FINISH_MERGED_PUSHED = f"{STATUS_OK} Merged and pushed `{{branch}}` -> `{{target}}`"
FINISH_MERGED_LOCAL = f"{STATUS_OK} Merged `{{branch}}` -> `{{target}}` (local only)"
FINISH_WORKTREE_CLEANUP_FAILED = f"\n{STATUS_WARN} Worktree cleanup failed: {{error}}"

FINISH_DISCARDED_ARCHIVED = f"{STATUS_OK} Branch `{{branch}}` discarded and archived"
FINISH_ARCHIVED_KEPT = f"""{STATUS_OK} Branch `{{branch}}` archived
Worktree kept for potential resume
Use /start to resume"""

FINISH_COMMIT_SENT = f"""{STATUS_PENDING} Asked Claude to commit\\. One moment\\.\\.\\.

Then run /finish"""


# --- Start Flow ---

START_SESSION_EXPIRED = "Session expired. Start again with /start"
START_PROJECT_NAME_PROMPT = "Send project name:"
START_DIR_CHOICE_PROMPT = "Directory `{path}` not found.\n\nWhat to do?"
START_GIT_SETUP_PROMPT = "Git setup?"
START_LAUNCH_CONFIRM = "Run Claude in `{path}`?"
START_CLAUDE_RUNNING = "Claude running: `{project}` in `{tmux_session}`"
START_TMUX_SELECT = "Multiple tmux sessions found. Select one:"
START_ERROR = "Error: {error}"
START_LAUNCHING = "Launching Claude..."
START_CONNECTED = "Connected to `{tmux_session}`"
START_SESSION_KILLED = "Session killed. Use /start to restart"

START_THREAD_RUNNING = f"""{STATUS_OK} Thread `{{thread_name}}` running

To see Claude UI: `tmux attach -t {{tmux_session}}`"""

START_ALREADY_RUNNING = f"""{STATUS_OK} Already running

To see Claude UI: `tmux attach -t {{tmux_name}}`"""

START_THREAD_UPGRADED = "Thread upgraded to `{thread_name}`"
START_TOPIC_REGISTERED = "Topic registered as `{thread_name}`"

START_SESSION_NOT_FOUND = f"{STATUS_WARN} Previous session not found"

START_WORKTREE_NOT_FOUND = f"{STATUS_WARN} Worktree not found: `{{path}}`"

START_WORKTREE_NOT_FOUND_BRANCH_EXISTS = f"""{STATUS_WARN} Worktree not found: `{{path}}`

Branch `{{branch}}` exists.

* Recreate worktree - recreate folder and resume session
* Resume in main - archive topic, continue in main
* Cancel"""

START_WORKTREE_NOT_FOUND_BRANCH_MISSING = f"""{STATUS_WARN} Worktree not found: `{{path}}`

Branch `{{branch}}` not found (merged?).

* Create new - create branch + worktree, resume session
* Resume in main - archive topic, continue in main
* Cancel"""

START_NEW_SESSION = f"{STATUS_PENDING} Starting new session..."
START_RECREATING_WORKTREE = f"{STATUS_PENDING} Recreating worktree..."
START_WORKTREE_RECREATED = f"{STATUS_OK} Worktree recreated. Use /start to launch"
START_WORKTREE_RECREATE_FAILED = f"{STATUS_ERR} Failed to recreate: {{error}}"

START_PATH_PROMPT = "Send project directory path:"
START_CLONE_URL_PROMPT = """Send repository URL:
* SSH: `git@github.com:user/repo.git`
* HTTPS: `https://github.com/user/repo.git`"""

START_GIT_VISIBILITY_PROMPT = "Repository visibility?"
START_RESTART_CONFIRM = "Restart session `{tmux_session}`?"


# --- Validation ---

VALIDATE_INVALID_NAME = f"{STATUS_ERR} Invalid name"
VALIDATE_NAME_TOO_LONG = f"{STATUS_ERR} Name too long (max {{max_len}} chars)"
VALIDATE_NAME_EXISTS = f"{STATUS_ERR} Name `{{name}}` already used"
VALIDATE_GIT_REQUIRED = f"{STATUS_ERR} Git repository required"
VALIDATE_UNCOMMITTED = f"{STATUS_WARN} Uncommitted changes"


# --- Errors ---

ERR_NOT_ADMIN = f"""{STATUS_ERR} Not admin. Your ID: `{{user_id}}`
Add your ID to ADMIN_IDS in .env"""

# Plain text version for callback popups (no markdown support)
ERR_NOT_ADMIN_POPUP = "[x] Not admin. Your ID: {user_id}"


# --- Branch Operations ---

BRANCH_PROJECT_NOT_REGISTERED = f"{STATUS_WARN} Project not registered. Use /start first"
BRANCH_GIT_REQUIRED = f"{STATUS_ERR} Git repository required for /branch_create"
BRANCH_CREATE_FROM_PROMPT = "Create branch from:"
BRANCH_PROJECT_NOT_FOUND_TOAST = "Project not found"

BRANCH_WORKTREE_NOT_FOUND_BASE = f"""{STATUS_WARN} Worktree not found, using {{default_branch}} as base

Branch name?

Send name or pick random"""

BRANCH_ALREADY_EXISTS = f"{STATUS_ERR} Branch `{{name}}` already exists"
BRANCH_DIR_EXISTS = f"{STATUS_ERR} Directory already exists: `{{path}}`"
BRANCH_UNCOMMITTED_CHANGES = f"{STATUS_WARN} Uncommitted changes detected"
BRANCH_UNCOMMITTED_IN_BASE = f"{STATUS_WARN} Uncommitted changes in {{base_branch}}"

BRANCH_COMMIT_SENT = f"""{STATUS_PENDING} Asked Claude to commit\\. One moment\\.\\.\\.

Then run `/branch_create {{branch_name}}`"""

BRANCH_CREATING = f"{STATUS_PENDING} Creating branch `{{name}}`..."
BRANCH_CREATED = f"{STATUS_OK} Branch `{{name}}` created"

BRANCH_FINISH_USE_FINISH = f"{STATUS_INFO} Use /finish to complete branches"


# --- Setup Flow v2 ---

# Base directory
SETUP_BASE_DIR_MISSING = f"""{STATUS_ERR} Configure base directory first

Set BASE_DIR in \\.env file:
`BASE_DIR=/home/user/dev`

Then restart the bot\\."""

# Admin rights (used for migration and check button)
SETUP_ADMIN_CHECK_FAILED = f"{STATUS_WARN} Still missing admin rights"

# Migration messages
MIGRATION_SUCCESS = f"""`[v]` Topics enabled

Multi\\-session mode unlocked:
/thread \\- new topic, same directory
/branch \\- isolated feature branch \\+ topic
/finish \\- merge and archive"""

MIGRATION_ADMIN_REQUIRED = f"""{STATUS_WARN} Grant admin rights to continue

Bot needs admin rights to:
• Rename chat to match project
• Manage topics for branches

Open chat settings → Edit → Administrators → Add bot as admin"""

ADMIN_RIGHTS_GRANTED = f"{STATUS_OK} Admin rights granted"

# Bot blocked while awaiting admin rights
BOT_ADMIN_RIGHTS_BLOCKED = f"""{STATUS_WARN} Bot needs admin rights

Grant admin rights to continue using the bot\\.

Open chat settings → Edit → Administrators → Add bot as admin"""

BOT_ADMIN_RIGHTS_BLOCKED_POPUP = "Grant admin rights first"

# Chat type errors
SETUP_PRIVATE_CHAT = f"{STATUS_ERR} Add bot to a group chat"
SETUP_CHANNEL_NOT_SUPPORTED = f"{STATUS_ERR} Channels not supported"
SETUP_CANCELLED = f"{STATUS_INFO} Setup cancelled\\. Use /start to begin again\\."
SETUP_ALREADY_IN_PROGRESS = f"{STATUS_INFO} Setup already in progress"

# Command blocking during setup
SETUP_COMMAND_BLOCKED = f"""{STATUS_WARN} Complete project setup first

Available commands:
• /start — restart setup
• /reset\\_all — cancel setup
• /help — get help"""

# Setup type selection
SETUP_CHOOSE_TYPE = "How would you like to set up this project?"

# Clone flow
SETUP_CLONE_URL_PROMPT = """Send repository URL:
• SSH: `git@github.com:user/repo.git`
• HTTPS: `https://github.com/user/repo.git`"""

SETUP_CLONE_PROGRESS = f"{STATUS_PENDING} Cloning repository\\.\\.\\."
SETUP_CLONE_FAILED = f"{STATUS_ERR} Clone failed: {{error}}"
SETUP_CLONE_SSH_HINT = "SSH key may not be configured. Try HTTPS URL instead."
SETUP_CLONE_AUTH_HINT = "Repository may be private. Check authentication."

# Folder selection
SETUP_FOLDER_SELECT = "Select folder to connect:"
SETUP_FOLDER_EMPTY = f"{STATUS_WARN} No folders found in `{{base_dir}}`"
SETUP_FOLDER_ALL_CONNECTED = f"""{STATUS_INFO} All folders are already connected

Start a new project instead\\?"""
SETUP_FOLDER_NOT_FOUND = f"{STATUS_ERR} Folder `{{name}}` not found"
SETUP_FOLDER_USE_BUTTONS = "Select a folder from the list above\\nor use \\[<< Go back\\] to return\\."

# View connected
SETUP_CONNECTED_HEADER = "Connected projects:"
SETUP_CONNECTED_EMPTY = "No projects connected yet"
SETUP_CONNECTED_TAP_HINT = "Tap chat name to open\\."
SETUP_CONNECTED_NO_LINK = "(no link)"

# New project
SETUP_PROJECT_NAME_PROMPT = """Project folder name?

Suggested: `{suggested}`

Or send custom name"""

SETUP_PROJECT_NAME_INVALID = f"{STATUS_ERR} Invalid name\\. Use letters, digits, \\- and \\_ only"
SETUP_PROJECT_EXISTS = f"""{STATUS_WARN} Folder `{{name}}` already exists

What to do\\?"""

# Git choice
SETUP_GIT_CHOICE = "Git setup for `{folder}`\\?"
SETUP_GIT_GH_NOT_INSTALLED = f"{STATUS_ERR} `gh` CLI not installed\\. Install from https://cli\\.github\\.com"
SETUP_GIT_GH_NOT_AUTH = f"{STATUS_ERR} `gh` not authenticated\\. Run `gh auth login` first"

# Rename
SETUP_RENAME_PROMPT = "Wow\\! You are setting up super chat\\!\n\nRename chat to `{name}` to align with project name\\?"
SETUP_RENAME_FAILED = f"{STATUS_WARN} Couldn't rename chat \\(missing permissions?\\)\nContinuing with project setup\\.\\.\\."

# Launch
SETUP_LAUNCH_PROGRESS = f"{STATUS_PENDING} Setting up project\\.\\.\\."
SETUP_LAUNCH_MKDIR_FAILED = f"{STATUS_ERR} Failed to create directory: {{error}}"
SETUP_LAUNCH_SUCCESS = f"""{STATUS_OK} Project `{{project}}` ready

Commands available:
• /esc — cancel operation
• /clear — clear context
• /auto_accept — toggle auto\\-accept
• /thread — new topic

To see Claude UI: `tmux attach \\-t {{tmux_name}}`"""

SETUP_LAUNCH_SUCCESS_THREAD = f"""{STATUS_OK} Thread `{{thread}}` running

To see Claude UI: `tmux attach \\-t {{tmux_name}}`"""

# Buttons
BTN_CLONE = "Clone repository"
BTN_CONNECT = "Connect to existing folder"
BTN_NEW = "Start new project"
BTN_CHECK_RIGHTS = "Check rights"
BTN_BACK_TO_FOLDERS = "<< Back to folders"
BTN_VIEW_CONNECTED = "View connected projects"
BTN_RENAME_YES = "Yes, rename"
BTN_RENAME_NO = "No"
BTN_GIT_INIT = "git init"
BTN_GIT_GH = "git init + gh repo create"
BTN_GIT_CLONE = "git clone"
BTN_GIT_NONE = "No git"
BTN_RETRY = "Retry"
BTN_CHANGE_URL = "Change URL"
BTN_USE_EXISTING = "Use existing"
BTN_DIFFERENT_NAME = "Different name"

# Stale button debounce (5 minutes per design)
STALE_BUTTON_SECONDS = 300


# --- DM Onboarding ---

DM_WELCOME = """Hey there

I'm Codogram — your Claude Code companion on Telegram"""

DM_SLIDE_1 = """📱 *Mobile*

Fire off tasks from your phone, work from anywhere

Claude runs on your server — all you need is Telegram"""

DM_SLIDE_2 = """⏰ *Async*

Start a task → do your thing → get notified when done

No more staring at terminal output"""

DM_SLIDE_3 = """👥 *Team*

Set up once — collaborate with teammates

Everyone sees what Claude does, can approve actions"""

# Validation - first message (will be edited)
DM_VALIDATION_CHECKING = f"{STATUS_PENDING} Checking environment..."

# Validation - results with checkmarks
DM_VALIDATION_OK = f"""{STATUS_OK} Environment ready

*Required:*
{{critical_checks}}

*Optional:*
{{optional_checks}}"""

DM_VALIDATION_ERROR = f"""{STATUS_ERR} Issues found

{{checks}}

Fix and hit "Recheck\""""

# Warnings shown after checks if any
DM_VALIDATION_WARNINGS = """
{warnings}"""

# CTA - separate message after validation passes
DM_CTA = """`[>>]` Next step

1. Create a group
2. Add bot with admin rights

Or add to existing one ↓
Bot will guide you from there

/dashboard — your projects"""

DM_MINI_STATUS = """Welcome back

Active projects: {projects}
Claude sessions: {sessions}

/dashboard — your projects
/intro — see intro again"""

DM_BOT_ADDED = """Added to "{chat_name}"
By: @{creator}"""

DM_BOT_ADDED_WITH_LINK = """Added to "{chat_name}"
Chat: {link}
By: @{creator}"""

# --- Dashboard ---

DASH_HEADER = "Projects"

DASH_PROJECT = """{num}. {chat_name}
   📁 {directory}
   👤 Owner: @{creator}
   👥 {members} members
   {status}"""

DASH_STATUS_ACTIVE = "🤖 {count} Claude sessions"
DASH_STATUS_INACTIVE = "💤 inactive"

DASH_FOOTER = "Total: {total} projects, {active} active sessions"

DASH_EMPTY = """Projects

No projects connected yet

Create a group and add me — I'll pick it up automatically"""

# --- DM Buttons ---

BTN_NEXT = "Next →"
BTN_PREV = "← Back"
BTN_HOW_TO_USE = "How to use?"
BTN_RECHECK = "Recheck"
BTN_REFRESH = "Refresh"
BTN_ADD_TO_GROUP = "Add to group"

# DM fallback for unknown commands
DM_UNKNOWN_COMMAND = "`[◉_◉]` Can't wait to try? Add me to a group chat"

# --- Emoji Pack ---

EMOJI_PACK_CREATED = """`[v]` Gift unlocked

✨ [Avatar pack]({pack_link}) ✨

Personalize topics with participant photos → [get pack]({pack_link})

New members will be added automatically\\."""

EMOJI_PACK_DISABLE_PROMPT = """`[?]` Disable avatar pack?

Pack will be deleted."""
EMOJI_PACK_BTN_DISABLE = "Yes, disable"
EMOJI_PACK_BTN_KEEP = "Keep it"

EMOJI_PACK_CREATE_PROMPT = """`[?]` Create avatar pack?

Will generate emoji from member avatars."""
EMOJI_PACK_BTN_CREATE = "Yes, create"
EMOJI_PACK_BTN_NOT_NOW = "Not now"

EMOJI_PACK_DELETED = "`[v]` Avatar pack disabled"
EMOJI_PACK_CREATING = "`[~]` Creating avatar pack..."
EMOJI_PACK_ERROR = "`[x]` Failed to create avatar pack: {error}"

# Hint in topic launch message (if feat_avatar_pack ON)
EMOJI_PACK_TOPIC_HINT = "→ Check this [pack]({pack_link}) to personalize your topic"
