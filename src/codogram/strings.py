"""All user-facing strings in one place.

See docs/specs/tone-of-voice.md for guidelines.
"""

# Status prefixes (always in backticks for markdown)
STATUS_OK = "`[v]`"
STATUS_ERR = "`[x]`"
STATUS_WARN = "`[!]`"
STATUS_PENDING = "`[~]`"


# --- Launch animation ---

LAUNCH_CREATING_TMUX = f"{STATUS_PENDING} Creating tmux session..."
LAUNCH_STARTING = f"{STATUS_PENDING} Starting Claude..."
LAUNCH_WAITING = f"{STATUS_PENDING} Waiting for Claude..."
LAUNCH_TIMEOUT = f"{STATUS_ERR} Timeout: Claude didn't start in 2 minutes"
LAUNCH_ERROR = f"{STATUS_ERR} Launch error: {{error}}"
LAUNCH_READY = f"{STATUS_OK} Claude ready"


# --- Session management ---

SESSION_BOUND = f"{STATUS_OK} New session bound"
SESSION_CLOSED = f"{STATUS_WARN} Claude session closed: {{name}}"
SESSION_NOT_FOUND = f"{STATUS_WARN} Session not found. Make sure Claude is running."
SESSION_EXPIRED = "Session expired"
SESSION_EXPIRED_START = "Session expired, start again with /start"
SESSION_STOPPED = "Session stopped. Use /start to launch."
SESSION_RESTART_CONFIRM = "Restart session `{tmux_name}`?"

NEW_SESSION = f"{STATUS_PENDING} Creating new session..."
CLEAR_SESSION = f"{STATUS_PENDING} Clearing session..."


# --- Project/Thread ---

PROJECT_NOT_FOUND = "Project not found"
PROJECT_NOT_REGISTERED = "Project not registered. Use /start"
PROJECT_NAME_INVALID = "Project name can only contain letters, digits, `-` and `_`."
PROJECT_NAME_PROMPT = "Send project name (e.g. `my-project`):"

THREAD_NOT_FOUND = "Thread not found"
THREAD_NOT_FOUND_START = "Thread not found. Use /start"
THREAD_CLOSED = "Thread closed"
THREAD_EXISTS = "Thread with name '{name}' already exists"
THREAD_NAME_INVALID = "Name can only contain letters, digits, - and _"
THREAD_CLOSE_CONFIRM = "Close thread '{name}'?\nTopic and tmux session will be deleted."
THREAD_NOT_LINKED = "This topic is not linked to a Claude session"
THREAD_TOPIC_ONLY = "This command can only be used in a topic"
THREAD_CONNECT_HINT = "Use /start or /session_new to connect Claude to this topic"


# --- Directory/Git ---

DIR_NOT_FOUND = "Directory `{path}` not found.\n\nWhat to do?"
DIR_NOT_EXISTS = "Directory `{path}` does not exist."
DIR_CREATED = "Directory `{path}` created."
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
CLAUDE_ATTACH = "Attach: `tmux attach -t {tmux_name}`"
CLAUDE_NOT_RUNNING = "Claude not running in `{cwd}`.\n\nLaunch?"
CLAUDE_CONNECTED = "Connected to tmux: `{tmux_session}`"
CLAUDE_NO_SESSION = "No active Claude session. Use /start to launch."
CLAUDE_TMUX_NOT_FOUND = "tmux session not found. Start Claude in terminal."
CLAUDE_NO_RESTART = "No active session to restart."


# --- Misc ---

LAUNCH_IN_PROGRESS = "Launch already in progress..."
CANCELLED = "Cancelled"
TOPICS_REQUIRED = "This chat doesn't support topics. Enable Topics in group settings."
TOPIC_CREATE_ERROR = "Error creating topic: {error}"
TOPIC_DELETE_ERROR = "Error deleting topic: {error}"


# --- File input ---

FILE_AUDIO_VIDEO_NOT_SUPPORTED = f"{STATUS_WARN} Video and audio not supported yet. Coming soon with Whisper!"
FILE_TYPE_NOT_SUPPORTED = "This file type is not supported"
FILE_TOO_LARGE = "File too large. Max 20MB"
FILE_DOWNLOAD_FAILED = "Download failed. Try again"


# --- Resume (deprecated) ---

RESUME_NOT_SUPPORTED_MULTI = f"{STATUS_WARN} /resume not supported in multi-session mode.\nUse /session_new for a new session."
RESUME_NOT_SUPPORTED = f"{STATUS_WARN} /resume not supported.\nUse /start to connect to existing session."


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
