# Setup Flow v2 Tests

Setup flow handles initial project configuration when bot is added to a new chat.

**Triggers:**
1. Bot added to chat (`my_chat_member` event)
2. `/start` in chat without registered project
3. Any message in chat without registered project

**FSM States:**
- `SetupFlow.awaiting_admin_rights` - user needs to grant admin rights
- `SetupFlow.awaiting_setup_type` - Choose: Clone / Connect / New
- `SetupFlow.awaiting_clone_url` - Enter git URL
- `SetupFlow.awaiting_folder_select` - Select existing folder
- `SetupFlow.viewing_connected_projects` - View connected projects list
- `SetupFlow.awaiting_project_name` - Enter or select project name
- `SetupFlow.awaiting_git_choice` - Choose git setup option
- `SetupFlow.awaiting_rename_confirm` - Confirm chat rename
- `SetupFlow.launching` - Setting up project (blocking state)

---

## TC-SETUP-001: Setup flow triggers on /start in new chat

**Tags:** smoke, critical, setup
**Preconditions:** Chat has no registered project, BASE_DIR configured in `.env`

**Setup:**
```bash
# Ensure chat is not registered
cat ~/.codogram/config.json | jq '.projects' | grep -v TEST_CHAT_ID

# Ensure BASE_DIR is configured
grep BASE_DIR /home/superbereza/dev/codogram/.env
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 3s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI (if bot not admin): Message contains "Grant admin rights to continue" with `[Check rights]` button
- UI (if bot is admin): Message "How would you like to set up this project?" with buttons:
  - `[Clone repository]`
  - `[Connect to existing folder]`
  - `[Start new project]`
- State: FSM state is `SetupFlow.awaiting_admin_rights` or `SetupFlow.awaiting_setup_type`

---

## TC-SETUP-002: Admin rights check flow

**Tags:** critical, setup, admin
**Preconditions:** Bot is not admin in test chat

**Setup:**
```bash
# ASK USER: "Please remove bot's admin rights in the test chat before this test"
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=2)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Message contains "Grant admin rights to continue"
- UI: Instructions about admin rights: "Bot needs admin rights to: Rename chat, Manage topics"
- UI: Button `[Check rights]`

**Steps (continued):**
```python
# ASK USER: "Please grant admin rights to the bot in Telegram, then continue"
# Wait for user confirmation
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Check rights")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected (after granting rights):**
- UI: Setup type selection appears with Clone/Connect/New buttons
- State: FSM state is `SetupFlow.awaiting_setup_type`

**Expected (if rights not granted):**
- UI: Message "Still missing admin rights"
- UI: `[Check rights]` button still present

---

## TC-SETUP-003: Clone flow - valid URL

**Tags:** critical, setup, clone
**Preconditions:** Bot has admin rights, setup type selection visible

**Setup:**
```bash
# Ensure no directory with target name exists
ls -la /home/superbereza/dev/ | grep -v "test-clone-repo"
```

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Clone repository")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Message "Send repository URL:" with SSH and HTTPS examples
- UI: Button `[<< Go back]`

**Steps (continued):**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="https://github.com/anthropics/anthropic-cookbook.git")
# Wait 30s (clone may take time)
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=5)
```

**Expected:**
- UI: Progress message "Cloning repository..."
- UI: Success message contains project name `anthropic-cookbook`
- UI: Success message contains `tmux attach -t claude-anthropic-cookbook`
- State: Project registered in config with `cwd` set
- State: tmux session exists: `tmux has-session -t claude-anthropic-cookbook`

**Cleanup:**
```bash
# Remove test project
tmux kill-session -t claude-anthropic-cookbook 2>/dev/null || true
rm -rf /home/superbereza/dev/anthropic-cookbook
# Remove from config (manual or via /reset_all)
```

---

## TC-SETUP-004: Clone flow - invalid URL

**Tags:** critical, setup, clone, validation
**Preconditions:** Bot has admin rights, clone URL prompt visible

**Setup:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Clone repository")
# Wait 2s
```

**Steps (wiki URL):**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="https://github.com/user/repo/wiki/Page")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Error message contains "This is a wiki page, not a repository"
- UI: Prompt "Send valid repository URL:"
- State: FSM state remains `SetupFlow.awaiting_clone_url` (can retry)

**Steps (blob URL):**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="https://github.com/user/repo/blob/main/README.md")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Error message contains "This is a file link. Use repository URL"

**Steps (gist URL):**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="https://gist.github.com/user/abc123")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Error message contains "Gists cannot be cloned as projects"

**Steps (invalid format):**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="ftp://invalid-protocol.com/repo")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Error message contains "Invalid URL. Use https:// or git@ format"

---

## TC-SETUP-005: Connect flow - folder selection

**Tags:** critical, setup, connect
**Preconditions:** Bot has admin rights, folders exist in BASE_DIR

**Setup:**
```bash
# Ensure some folders exist in BASE_DIR
ls /home/superbereza/dev/ | head -10
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Connect to existing folder")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Message "Select folder to connect:"
- UI: List of folder buttons (e.g., `[codogram]`, `[scripts]`, etc.)
- UI: Pagination buttons if >10 folders: `[<] 1/N [>]`
- UI: Button `[View connected projects]`
- UI: Button `[<< Go back]`

**Steps (select folder):**
```python
# Select first available folder (adjust button_text as needed)
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="codogram")
# Wait 3s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected (if folder has .git):**
- UI: Rename prompt "Rename chat to `codogram`?" with `[Yes, rename]` `[No]` OR directly proceeds to launch
- State: Project setup continues

**Expected (if folder has no .git):**
- UI: Git choice screen "Git setup for `codogram`?"
- UI: Buttons: `[git init]`, `[git init + gh repo create]`, `[No git]`

---

## TC-SETUP-006: New project flow - suggested name

**Tags:** critical, setup, new
**Preconditions:** Bot has admin rights, setup type selection visible

**Setup:**
```bash
# Note the chat title for expected suggested name
# ASK USER: "What is the chat title?"
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Start new project")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Message "Project folder name?"
- UI: Suggested name derived from chat title
- UI: Button with suggested name (e.g., `[my-project-name]`)
- UI: Text "Or send custom name"
- UI: Button `[<< Go back]`

**Steps (click suggested):**
```python
# Click the suggested name button (text varies by chat)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
# Find and click the first non-navigation button
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_index=0)
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Git choice screen "Git setup for `{folder}`?"
- UI: Buttons for git options

---

## TC-SETUP-007: New project flow - custom name

**Tags:** critical, setup, new
**Preconditions:** Bot has admin rights, project name prompt visible

**Setup:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Start new project")
# Wait 2s
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="my-custom-test-project")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected (if name differs from chat title):**
- UI: Rename prompt "Rename chat to `my-custom-test-project`?"
- UI: Buttons `[Yes, rename]` `[No]`

**Steps (confirm rename):**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Yes, rename")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Git choice screen
- ASK USER: "Was the chat renamed to 'my-custom-test-project'?"

---

## TC-SETUP-008: Git choice - Init

**Tags:** critical, setup, git
**Preconditions:** Git choice screen visible

**Setup:**
```python
# Get to git choice via new project flow
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Start new project")
# Wait 2s
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="test-git-init")
# Wait for rename prompt or git choice
# Skip rename if shown
```

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="git init")
# Wait 10s for project setup
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=5)
```

**Expected:**
- UI: Progress message "Setting up project..."
- UI: Success message "Project `test-git-init` ready"
- UI: Commands list shown
- State: Directory created at `{BASE_DIR}/test-git-init`
- State: `.git` directory exists in project folder

**Verify:**
```bash
ls -la /home/superbereza/dev/test-git-init/.git
```

**Cleanup:**
```bash
tmux kill-session -t claude-test-git-init 2>/dev/null || true
rm -rf /home/superbereza/dev/test-git-init
```

---

## TC-SETUP-009: Git choice - GitHub

**Tags:** critical, setup, git, github
**Preconditions:** `gh` CLI installed and authenticated, git choice screen visible

**Setup:**
```bash
# Check gh CLI
which gh
gh auth status
```

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="git init + gh repo create")
# Wait 3s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Visibility choice "Repository visibility?"
- UI: Buttons `[Public]` `[Private]`

**Steps (select visibility):**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Private")
# Wait 20s for repo creation
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=5)
```

**Expected:**
- UI: Progress messages for git init and repo creation
- UI: Success message with project name
- State: GitHub repo created (verify via `gh repo view`)

**Cleanup:**
```bash
# Delete test repo
gh repo delete {username}/test-gh-init --yes 2>/dev/null || true
```

---

## TC-SETUP-010: Command blocked during setup

**Tags:** critical, setup, blocking
**Preconditions:** Setup flow in progress (any step after trigger)

**Setup:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
# Don't complete setup - stay at setup type selection
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/settings")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Message "Complete project setup first"
- UI: Available commands listed: /start, /reset_all, /help

**Steps (verify allowed commands):**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/help")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Help message displayed (not blocked)

---

## TC-SETUP-011: /start restarts setup during active flow

**Tags:** critical, setup, restart
**Preconditions:** Setup flow in progress at some step

**Setup:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Clone repository")
# Wait 2s - now at clone URL prompt
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Flow restarts - shows setup type selection (Clone/Connect/New buttons)
- State: FSM state reset to `SetupFlow.awaiting_setup_type`

---

## TC-SETUP-012: BASE_DIR not configured

**Tags:** critical, setup, config
**Preconditions:** BASE_DIR not set or invalid in `.env`

**Setup:**
```bash
# Temporarily remove or comment BASE_DIR in .env
# ASK USER: "Please comment out BASE_DIR in .env and restart bot"
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Error message "Configure base directory first"
- UI: Instructions to set BASE_DIR in .env file
- State: Setup flow blocked

**Cleanup:**
```bash
# ASK USER: "Please restore BASE_DIR in .env and restart bot"
```

---

## TC-SETUP-013: Go back navigation

**Tags:** smoke, setup, navigation
**Preconditions:** Bot has admin rights

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Clone repository")
# Wait 2s - at clone URL prompt
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="<< Go back")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Back at setup type selection (Clone/Connect/New buttons)

**Steps (continue to new project, then back):**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Start new project")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="<< Go back")
# Wait 2s
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Back at setup type selection

---

## TC-SETUP-014: Folder selection pagination

**Tags:** full, setup, pagination
**Preconditions:** BASE_DIR has >10 folders

**Setup:**
```bash
# Count folders in BASE_DIR
ls -d /home/superbereza/dev/*/ | wc -l
# Should be >10 for this test
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Connect to existing folder")
# Wait 2s
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Folder list with first 10 folders
- UI: Pagination: `[<] 1/N [>]` where N > 1

**Steps (navigate pages):**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text=">")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=2)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Next page of folders shown
- UI: Pagination shows `[<] 2/N [>]`

---

## TC-SETUP-015: View connected projects

**Tags:** full, setup, connect
**Preconditions:** At least one project already connected

**Setup:**
```bash
# Verify connected projects exist
cat ~/.codogram/config.json | jq '.projects | keys'
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Connect to existing folder")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="View connected projects")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Message "Connected projects:"
- UI: List of connected projects with chat links (e.g., "codogram -> Chat Name")
- UI: Button `[<< Back to folders]`

---

## TC-SETUP-016: Project name validation - invalid characters

**Tags:** full, setup, validation
**Preconditions:** At project name prompt

**Setup:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Start new project")
# Wait 2s
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="invalid name with spaces!")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Error "Invalid name. Use letters, digits, - and _ only"
- State: Can retry with valid name

---

## TC-SETUP-017: Folder already exists handling

**Tags:** full, setup, new
**Preconditions:** Folder with same name already exists in BASE_DIR

**Setup:**
```bash
# Create a test folder
mkdir -p /home/superbereza/dev/existing-test-folder
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Start new project")
# Wait 2s
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="existing-test-folder")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Warning "Folder `existing-test-folder` already exists"
- UI: Buttons `[Use existing]` `[Different name]`

**Cleanup:**
```bash
rmdir /home/superbereza/dev/existing-test-folder
```

---

## TC-SETUP-018: gh CLI not installed

**Tags:** full, setup, git, github
**Preconditions:** gh CLI not in PATH

**Setup:**
```bash
# Temporarily move gh to simulate not installed
# ASK USER: "Do you want to test gh not installed scenario? This requires temporarily renaming gh binary"
```

**Steps:**
```python
# At git choice screen
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="git init + gh repo create")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Error "`gh` CLI not installed. Install from https://cli.github.com"

---

## TC-SETUP-019: Clone with SSH key issue

**Tags:** full, setup, clone, error
**Preconditions:** SSH key not configured for GitHub

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Clone repository")
# Wait 2s
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="git@github.com:nonexistent-user-12345/nonexistent-repo.git")
# Wait 15s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Clone error message
- UI: Hint about SSH key or authentication
- UI: Buttons `[Retry]` `[Change URL]` `[<< Go back]`

---

## TC-SETUP-020: Cancel button stale after 5 minutes

**Tags:** full, setup, debounce
**Preconditions:** Setup buttons shown more than 5 minutes ago

**Setup:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
# ASK USER: "Wait 5+ minutes before clicking any button, then continue"
```

**Steps:**
```python
# After waiting 5+ minutes
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="Clone repository")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: Button click is ignored (stale button debounce)
- State: No state change

---

## TC-SETUP-021: Private chat blocked

**Tags:** smoke, setup, blocking
**Preconditions:** Bot is accessible via private chat

**Steps:**
```python
# Send /start to bot's private chat (not a group)
mcp__telegram__send_message(chat_id=BOT_PRIVATE_CHAT_ID, message="/start")
# Wait 2s
mcp__telegram__list_messages(chat_id=BOT_PRIVATE_CHAT_ID, limit=3)
```

**Expected:**
- UI: Error "Add bot to a group chat"
- State: Setup not started

---

## TC-SETUP-022: Successful launch announcement

**Tags:** smoke, setup, launch
**Preconditions:** Complete a full setup flow successfully

**Steps:**
```python
# Complete full setup (clone, connect, or new)
# ... previous steps to complete setup ...
# After success
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=5)
```

**Expected (in forum chat):**
- UI: Success message "Project `{name}` ready"
- UI: Commands list includes:
  - `/esc` - cancel operation
  - `/clear` - clear context
  - `/auto_accept` - toggle auto-accept
  - `/thread` - new topic
  - `/branch` - new branch + topic (forum only)
  - `/finish` - merge and archive (forum only)
- UI: Terminal command `tmux attach -t claude-{project}`

**Expected (in non-forum chat):**
- UI: Same as above but WITHOUT `/branch` and `/finish` commands

---

## TC-SETUP-023: /reset_all cancels setup

**Tags:** critical, setup, reset
**Preconditions:** Setup flow in progress

**Setup:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 2s
# Don't complete - stay at setup type selection
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/reset_all")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=3)
```

**Expected:**
- UI: "Reset complete. Use /start to begin."
- State: FSM state cleared
- State: Project removed from config (if partially created)
