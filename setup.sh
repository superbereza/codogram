#!/bin/bash
set -e

# Restore cursor on exit (in case of Ctrl+C during selector)
trap 'tput cnorm 2>/dev/null' EXIT

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

print_step() {
    echo -e "\n${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Run command with progress indicator (hides verbose output)
# Usage: run_with_progress "message" command args...
run_with_progress() {
    local msg="$1"
    shift
    local tmp_out=$(mktemp)

    printf "  ⏳ ${msg}..."

    if "$@" > "$tmp_out" 2>&1; then
        printf "\r                                                  \r"
        print_success "$msg"
        rm -f "$tmp_out"
        return 0
    else
        local exit_code=$?
        printf "\r                                                  \r"
        print_error "$msg"
        echo -e "${DIM}Output:${NC}"
        tail -10 "$tmp_out"
        rm -f "$tmp_out"
        return $exit_code
    fi
}

# Interactive multi-select using bash select (works everywhere)
# Usage: multiselect "prompt" result_array options_array descriptions_array
multiselect() {
    local prompt="$1"
    local -n _result=$2
    local -n _options=$3
    local -n _descriptions=$4
    local count=${#_options[@]}

    echo -e "\n${BLUE}==>${NC} $prompt"
    echo -e "${DIM}    Enter numbers to toggle, 'a' for all, 'n' for none, Enter when done${NC}\n"

    # Initialize all as selected
    local selected=()
    for ((i=0; i<count; i++)); do
        selected+=("true")
    done

    # Show initial state
    for ((i=0; i<count; i++)); do
        if [[ "${selected[$i]}" == "true" ]]; then
            echo -e "  ${GREEN}[✓]${NC} $((i+1))) ${_options[$i]} ${DIM}— ${_descriptions[$i]}${NC}"
        else
            echo -e "  [ ] $((i+1))) ${_options[$i]} ${DIM}— ${_descriptions[$i]}${NC}"
        fi
    done

    while true; do
        echo ""
        read -p "Toggle (1-$count), [a]ll, [n]one, Enter to confirm: " choice

        case "$choice" in
            [1-9]|[1-9][0-9])
                local idx=$((choice - 1))
                if [[ $idx -ge 0 && $idx -lt $count ]]; then
                    if [[ "${selected[$idx]}" == "true" ]]; then
                        selected[$idx]="false"
                    else
                        selected[$idx]="true"
                    fi
                fi
                ;;
            a|A)
                for ((i=0; i<count; i++)); do
                    selected[$i]="true"
                done
                ;;
            n|N)
                for ((i=0; i<count; i++)); do
                    selected[$i]="false"
                done
                ;;
            d|D|"")
                break
                ;;
        esac

        # Calculate actual terminal lines to clear (accounting for wrapping)
        local cols=$(tput cols 2>/dev/null || echo 80)
        local lines_to_clear=2  # prompt + empty line

        for ((i=0; i<count; i++)); do
            # Approximate line length (without ANSI codes)
            local line_text="  [x] $((i+1))) ${_options[$i]} — ${_descriptions[$i]}"
            local line_len=${#line_text}
            # Ceiling division: how many terminal rows this line takes
            local rows=$(( (line_len + cols - 1) / cols ))
            lines_to_clear=$((lines_to_clear + rows))
        done

        for ((i=0; i<lines_to_clear; i++)); do
            printf "\e[2K\r\e[1A"
        done
        printf "\e[2K\r"

        # Redraw options
        for ((i=0; i<count; i++)); do
            if [[ "${selected[$i]}" == "true" ]]; then
                echo -e "  ${GREEN}[✓]${NC} $((i+1))) ${_options[$i]} ${DIM}— ${_descriptions[$i]}${NC}"
            else
                echo -e "  [ ] $((i+1))) ${_options[$i]} ${DIM}— ${_descriptions[$i]}${NC}"
            fi
        done
    done

    # Build result
    _result=()
    for ((i=0; i<count; i++)); do
        if [[ "${selected[$i]}" == "true" ]]; then
            _result+=("${_options[$i]}")
        fi
    done
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)

# Disable interactive prompts for apt on Linux
if [[ "$OS" == "linux" ]]; then
    export DEBIAN_FRONTEND=noninteractive
fi

# Use sudo only if not root
if [[ $EUID -eq 0 ]]; then
    SUDO=""
else
    SUDO="$SUDO"
fi

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════╗"
echo "║         Codogram Setup Script         ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"

if [[ "$OS" == "unknown" ]]; then
    print_error "Unsupported OS: $OSTYPE"
    print_warning "This script supports Linux and macOS only."
    exit 1
fi

# Check we're in the right directory
if [[ ! -f "pyproject.toml" ]]; then
    print_error "pyproject.toml not found"
    print_warning "Please run this script from the codogram directory."
    exit 1
fi

print_success "Detected OS: $OS"

# Check all dependencies
print_step "Checking dependencies..."

MISSING=()
DESCRIPTIONS=()

# Check Python >= 3.10
check_python_version() {
    if command -v python3 &> /dev/null; then
        local version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        local major=$(echo "$version" | cut -d. -f1)
        local minor=$(echo "$version" | cut -d. -f2)
        # major > 3 OR (major == 3 AND minor >= 10)
        if [[ $major -gt 3 ]] || ([[ $major -eq 3 ]] && [[ $minor -ge 10 ]]); then
            return 0
        fi
    fi
    return 1
}

if check_python_version; then
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    print_success "python3 found ($PY_VERSION)"
else
    if command -v python3 &> /dev/null; then
        PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        print_warning "python3 found ($PY_VERSION) but need >= 3.10"
    else
        print_warning "python3 not found"
    fi
    MISSING+=("python3")
    DESCRIPTIONS+=("required, Python >= 3.10")
fi

# Check brew on macOS (needed for installing other deps)
if [[ "$OS" == "macos" ]]; then
    if command -v brew &> /dev/null; then
        print_success "brew found"
    else
        print_warning "brew not found"
        MISSING+=("brew")
        DESCRIPTIONS+=("required on macOS, package manager for installing dependencies")
    fi
fi

# Check tmux
if command -v tmux &> /dev/null; then
    print_success "tmux found"
else
    print_warning "tmux not found"
    MISSING+=("tmux")
    DESCRIPTIONS+=("required, terminal multiplexer for Claude sessions")
fi

# Check git
if command -v git &> /dev/null; then
    print_success "git found"
else
    print_warning "git not found"
    MISSING+=("git")
    DESCRIPTIONS+=("optional, version control, git init/clone")
fi

# Check gh
if command -v gh &> /dev/null; then
    print_success "gh found"
else
    print_warning "gh not found"
    MISSING+=("gh")
    DESCRIPTIONS+=("optional, GitHub CLI, create repos from Telegram")
fi

# Check Claude Code
if command -v claude &> /dev/null; then
    print_success "claude found"
else
    print_warning "claude not found"
    MISSING+=("claude")
    DESCRIPTIONS+=("required, Claude Code CLI, AI coding assistant")
fi

# Interactive selector for missing dependencies
INSTALL_LATER=()
MACOS_PYTHON_SHOWN=false

if [[ ${#MISSING[@]} -eq 0 ]]; then
    echo ""
    print_success "All dependencies found!"
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
    TO_INSTALL=()
    multiselect "Select what to install:" TO_INSTALL MISSING DESCRIPTIONS

    echo ""

    # Check if required deps were skipped
    REQUIRED_SKIPPED=()

    if [[ " ${MISSING[*]} " =~ " python3 " ]] && [[ ! " ${TO_INSTALL[*]} " =~ " python3 " ]]; then
        REQUIRED_SKIPPED+=("python3")
    fi

    if [[ " ${MISSING[*]} " =~ " brew " ]] && [[ ! " ${TO_INSTALL[*]} " =~ " brew " ]]; then
        REQUIRED_SKIPPED+=("brew")
    fi

    if [[ " ${MISSING[*]} " =~ " tmux " ]] && [[ ! " ${TO_INSTALL[*]} " =~ " tmux " ]]; then
        REQUIRED_SKIPPED+=("tmux")
    fi

    if [[ " ${MISSING[*]} " =~ " claude " ]] && [[ ! " ${TO_INSTALL[*]} " =~ " claude " ]]; then
        REQUIRED_SKIPPED+=("claude")
    fi

    # Handle skipped required dependencies
    if [[ ${#REQUIRED_SKIPPED[@]} -gt 0 ]]; then
        echo ""
        print_warning "These are required for Codogram to work:"
        for dep in "${REQUIRED_SKIPPED[@]}"; do
            echo -e "  • ${YELLOW}${dep}${NC}"
        done
        echo ""
        echo "What would you like to do?"
        echo ""
        echo "  [1] Install them now"
        echo "  [2] I'll install later myself"
        echo ""
        read -p "Choice [1/2]: " -n 1 -r
        echo ""

        if [[ $REPLY == "1" ]]; then
            # Add back to install list
            for dep in "${REQUIRED_SKIPPED[@]}"; do
                TO_INSTALL+=("$dep")
            done
        else
            # Will show instructions at the end
            INSTALL_LATER=("${REQUIRED_SKIPPED[@]}")
            print_warning "Codogram won't fully work without these dependencies."
            echo ""
        fi
    fi

    # Install selected tools (brew first if needed)
    # Sort: brew should be installed first on macOS
    SORTED_INSTALL=()
    for tool in "${TO_INSTALL[@]}"; do
        if [[ "$tool" == "brew" ]]; then
            SORTED_INSTALL=("brew" "${SORTED_INSTALL[@]}")
        else
            SORTED_INSTALL+=("$tool")
        fi
    done

    for tool in "${SORTED_INSTALL[@]}"; do
        case $tool in
            brew)
                print_step "Installing Homebrew..."
                echo ""
                echo "  Homebrew is the package manager for macOS."
                echo "  It will be installed to /opt/homebrew (Apple Silicon) or /usr/local (Intel)."
                echo ""
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                print_success "Homebrew installed"
                # Add to PATH for this session
                if [[ -f "/opt/homebrew/bin/brew" ]]; then
                    eval "$(/opt/homebrew/bin/brew shellenv)"
                elif [[ -f "/usr/local/bin/brew" ]]; then
                    eval "$(/usr/local/bin/brew shellenv)"
                fi
                ;;
            python3)
                if [[ "$OS" == "linux" ]]; then
                    run_with_progress "Updating apt" $SUDO apt-get update
                    run_with_progress "Installing software-properties-common" $SUDO apt-get install -y software-properties-common
                    run_with_progress "Adding deadsnakes PPA" $SUDO add-apt-repository -y ppa:deadsnakes/ppa
                    run_with_progress "Updating apt" $SUDO apt-get update
                    run_with_progress "Installing Python 3.12" $SUDO apt-get install -y python3.12 python3.12-venv
                    # Create python3 symlink if needed
                    if ! command -v python3 &> /dev/null; then
                        sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
                    fi
                else
                    # macOS - don't auto-install, show warning once
                    echo ""
                    print_warning "Python >= 3.10 required. Please install manually:"
                    echo ""
                    echo "  Via Homebrew:"
                    echo -e "    ${YELLOW}brew install python${NC}"
                    echo ""
                    echo "  Or via pyenv:"
                    echo -e "    ${YELLOW}brew install pyenv${NC}"
                    echo -e "    ${YELLOW}pyenv install 3.12${NC}"
                    echo ""
                    echo "  Guide: https://docs.python-guide.org/starting/install3/osx/"
                    echo ""
                    # Mark as not installed (will be excluded from SKIPPED since it's in TO_INSTALL)
                    MACOS_PYTHON_SHOWN=true
                fi
                ;;
            tmux)
                if [[ "$OS" == "linux" ]]; then
                    run_with_progress "Installing tmux" $SUDO apt-get install -y tmux
                else
                    run_with_progress "Installing tmux" brew install tmux
                fi
                ;;
            git)
                if [[ "$OS" == "linux" ]]; then
                    run_with_progress "Installing git" $SUDO apt-get install -y git
                else
                    run_with_progress "Installing git" brew install git
                fi
                ;;
            gh)
                if [[ "$OS" == "linux" ]]; then
                    run_with_progress "Installing gh" $SUDO apt-get install -y gh
                else
                    run_with_progress "Installing gh" brew install gh
                fi
                echo ""
                print_warning "Don't forget to authenticate later:"
                echo -e "    ${YELLOW}gh auth login${NC}"
                echo ""
                ;;
            claude)
                if run_with_progress "Installing Claude Code CLI" bash -c "curl -fsSL https://claude.ai/install.sh | bash"; then
                    echo ""
                    print_warning "Don't forget to authenticate later:"
                    echo -e "    ${YELLOW}claude${NC}  (follow the login prompts)"
                    echo ""
                else
                    echo ""
                    echo "  Try manually:"
                    echo -e "    ${YELLOW}curl -fsSL https://claude.ai/install.sh | bash${NC}"
                    echo ""
                    INSTALL_LATER+=("claude")
                fi
                ;;
        esac
    done

    # Show manual install commands for skipped tools
    SKIPPED=()
    for dep in "${MISSING[@]}"; do
        if [[ ! " ${TO_INSTALL[*]} " =~ " ${dep} " ]]; then
            SKIPPED+=("$dep")
        fi
    done

    # Don't show Python again for macOS if already shown
    if [[ "$MACOS_PYTHON_SHOWN" == true ]]; then
        SKIPPED=("${SKIPPED[@]/python3/}")
    fi

    if [[ ${#SKIPPED[@]} -gt 0 ]]; then
        # Check if any are required (from INSTALL_LATER)
        if [[ ${#INSTALL_LATER[@]} -gt 0 ]]; then
            echo ""
            print_warning "Required dependencies to install before running:"
            echo ""
        else
            echo ""
            print_step "Manual install commands (for later):"
            echo ""
        fi

        for dep in "${SKIPPED[@]}"; do
            # Skip empty entries
            [[ -z "$dep" ]] && continue

            # Mark required deps
            LABEL=""
            if [[ " ${INSTALL_LATER[*]} " =~ " ${dep} " ]]; then
                LABEL=" ${RED}(required)${NC}"
            fi

            case $dep in
                brew)
                    echo -e "  brew:${LABEL}"
                    echo -e "    ${YELLOW}/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"${NC}"
                    ;;
                python3)
                    if [[ "$OS" == "linux" ]]; then
                        echo -e "  python:${LABEL}"
                        echo -e "    ${YELLOW}sudo add-apt-repository ppa:deadsnakes/ppa${NC}"
                        echo -e "    ${YELLOW}sudo apt install python3.12 python3.12-venv${NC}"
                    else
                        echo -e "  python:${LABEL}"
                        echo -e "    ${YELLOW}brew install python${NC}  or  ${YELLOW}pyenv install 3.12${NC}"
                        echo -e "    Guide: https://docs.python-guide.org/starting/install3/osx/"
                    fi
                    ;;
                tmux)
                    if [[ "$OS" == "linux" ]]; then
                        echo -e "  tmux:${LABEL}    ${YELLOW}sudo apt install tmux${NC}"
                    else
                        echo -e "  tmux:${LABEL}    ${YELLOW}brew install tmux${NC}"
                    fi
                    ;;
                git)
                    if [[ "$OS" == "linux" ]]; then
                        echo -e "  git:     ${YELLOW}sudo apt install git${NC}"
                    else
                        echo -e "  git:     ${YELLOW}brew install git${NC}"
                    fi
                    ;;
                gh)
                    if [[ "$OS" == "linux" ]]; then
                        echo -e "  gh:      ${YELLOW}sudo apt install gh${NC}"
                    else
                        echo -e "  gh:      ${YELLOW}brew install gh${NC}"
                    fi
                    echo -e "           ${YELLOW}gh auth login${NC}"
                    ;;
                claude)
                    echo -e "  claude:${LABEL}  ${YELLOW}curl -fsSL https://claude.ai/install.sh | bash${NC}"
                    ;;
            esac
        done
        echo ""
    fi
fi

# Create virtual environment
print_step "Setting up Python virtual environment..."

# Find suitable Python (3.10+)
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &> /dev/null; then
        version=$($cmd -c 'import sys; print(f"{sys.version_info.minor}")')
        if [[ $version -ge 10 ]]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    print_error "Python >= 3.10 not found. Please install it first."
    exit 1
fi

if [[ ! -d "venv" ]]; then
    $PYTHON_CMD -m venv venv
    print_success "Virtual environment created (using $PYTHON_CMD)"
else
    # Check if existing venv is valid (both python and pip must work)
    if ./venv/bin/python3 --version > /dev/null 2>&1 && ./venv/bin/pip --version > /dev/null 2>&1; then
        print_success "Virtual environment already exists"
    else
        print_warning "Virtual environment broken, recreating..."
        rm -rf venv
        $PYTHON_CMD -m venv venv
        print_success "Virtual environment recreated"
    fi
fi

# Install dependencies using venv pip directly
run_with_progress "Upgrading pip" ./venv/bin/pip install --upgrade pip
run_with_progress "Installing dependencies" ./venv/bin/pip install -e .

# Configure .env
print_step "Configuring environment..."

if [[ -f ".env" ]]; then
    print_warning ".env file already exists"
    read -p "Overwrite? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_success "Keeping existing .env"
        SKIP_ENV=true
    fi
fi

if [[ -z "$SKIP_ENV" ]]; then
    echo ""
    echo -e "${BLUE}To create a Telegram bot:${NC}"
    echo "1. Open @BotFather in Telegram: https://t.me/BotFather"
    echo "2. Send /newbot"
    echo "3. Follow the instructions to get your token"
    echo ""

    read -p "Enter your Telegram bot token: " TELEGRAM_TOKEN

    if [[ -z "$TELEGRAM_TOKEN" ]]; then
        print_error "Token is required!"
        exit 1
    fi

    echo ""
    echo -e "${BLUE}To get your Telegram user ID:${NC}"
    echo "1. Open @userinfobot in Telegram: https://t.me/userinfobot"
    echo "2. Send any message"
    echo "3. Copy the 'Id' number from the response"
    echo ""

    read -p "Enter your Telegram user ID: " ADMIN_ID

    if [[ -z "$ADMIN_ID" ]]; then
        print_error "User ID is required!"
        exit 1
    fi

    # Base directory is parent of codogram
    BASE_DIR="$(cd .. && pwd)"

    # Create .env
    cat > .env << EOF
TELEGRAM_TOKEN=$TELEGRAM_TOKEN
ADMIN_IDS=$ADMIN_ID
BASE_DIR=$BASE_DIR
LOG_LEVEL=INFO
EOF

    print_success ".env file created"
fi

# Create logs directory
mkdir -p logs

# Done!
echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════╗"
echo "║           Setup Complete!             ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"

echo ""
echo "To start the bot:"
echo -e "  ${YELLOW}./stop-and-restart.sh${NC}"
echo ""
echo "Then in Telegram:"
echo "  1. Open chat with your bot (or create a group with it)"
echo "  2. Send /start"
echo ""
echo "See docs/setup.md for more information."
