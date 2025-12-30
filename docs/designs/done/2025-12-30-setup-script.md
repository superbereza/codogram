# Setup Script Design

## Проблема

Установка Codogram требует нескольких шагов:
- Установка Python >= 3.10, tmux, git, gh, Claude Code CLI
- Создание venv и установка зависимостей
- Настройка .env (токен бота, admin ID)

Пользователю нужно вручную искать инструкции для своей ОС.

## Решение

Интерактивный `setup.sh` скрипт:
1. Определяет ОС (Linux/macOS)
2. Проверяет зависимости
3. Показывает интерактивный селектор для установки
4. Создаёт venv и ставит Python пакеты
5. Запрашивает токен бота и admin ID
6. Создаёт .env файл

## Зависимости

| Tool | Status | Linux | macOS |
|------|--------|-------|-------|
| python3 | required | deadsnakes PPA | warning + ссылка |
| brew | required (macOS) | — | автоустановка |
| tmux | required | apt | brew |
| git | optional | apt | brew |
| gh | optional | apt | brew |
| claude | required | curl installer | curl installer |

## Интерактивный селектор

Числа для toggle, работает везде (включая Docker):

```
==> Select what to install:
    Enter numbers to toggle, 'a' for all, 'n' for none, Enter when done

  [✓] 1) python3 — required, Python >= 3.10
  [✓] 2) tmux — required, terminal multiplexer
  [ ] 3) git — optional, version control
  [✓] 4) claude — required, Claude Code CLI

Toggle (1-4), [a]ll, [n]one, Enter to confirm:
```

### Почему не стрелки?

Arrow-key selector с `read -rsn1` не работает в Docker и некоторых терминалах.

### Очистка экрана при redraw

Проблема: строки могут переноситься в узких терминалах (58 cols в tmux).

**Неработающие подходы:**
- `\033[s` / `\033[u` (cursor save/restore) — нестабильно
- Фиксированное кол-во строк — не учитывает переносы

**Решение:** вычисляем реальное количество строк:

```bash
local cols=$(tput cols 2>/dev/null || echo 80)
local lines_to_clear=2  # prompt + empty line

for ((i=0; i<count; i++)); do
    local line_text="  [x] $((i+1))) ${_options[$i]} — ${_descriptions[$i]}"
    local line_len=${#line_text}
    local rows=$(( (line_len + cols - 1) / cols ))  # ceiling division
    lines_to_clear=$((lines_to_clear + rows))
done

# Очищаем снизу вверх
for ((i=0; i<lines_to_clear; i++)); do
    printf "\e[2K\r\e[1A"  # clear line, CR, move up
done
printf "\e[2K\r"
```

### ANSI sequences
- `\e[2K` — очистить всю строку
- `\r` — carriage return (курсор в колонку 0)
- `\e[1A` — курсор вверх на 1 строку

## Особенности

### macOS Python
Не устанавливаем автоматически — показываем инструкции:
```
! Python >= 3.10 required. Please install manually:

  Via Homebrew:
    brew install python

  Or via pyenv:
    brew install pyenv
    pyenv install 3.12

  Guide: https://docs.python-guide.org/starting/install3/osx/
```

### Required dependencies
Если пользователь снял галочку с required:
```
! These are required for Codogram to work:
  • claude

What would you like to do?

  [1] Install them now
  [2] I'll install later myself
```

### Безопасность
- `trap 'tput cnorm' EXIT` — восстановление курсора при Ctrl+C
- Проверка директории (pyproject.toml)
- Не ломаем системный Python на macOS
- Спрашиваем перед перезаписью .env

### venv валидация

Проверяем И python И pip — pip имеет hardcoded shebang:
```bash
if ./venv/bin/python3 --version > /dev/null 2>&1 && \
   ./venv/bin/pip --version > /dev/null 2>&1; then
    print_success "Virtual environment already exists"
else
    # Recreate if either is broken
fi
```

Это важно когда venv примонтирован с другой машины (Docker).

### sudo handling

В Docker обычно уже root, sudo не нужен:
```bash
if [[ $EUID -eq 0 ]]; then
    SUDO=""
else
    SUDO="sudo -E"
fi

$SUDO apt-get install -y ...
```

### run_with_progress

Скрываем verbose output, показываем только на ошибку:
```bash
run_with_progress() {
    local msg="$1"; shift
    local tmp_out=$(mktemp)
    printf "  ⏳ ${msg}..."
    if "$@" > "$tmp_out" 2>&1; then
        printf "\r...\r"
        print_success "$msg"
    else
        print_error "$msg"
        tail -10 "$tmp_out"
    fi
    rm -f "$tmp_out"
}
```

### apt noninteractive
```bash
export DEBIAN_FRONTEND=noninteractive
```

## Flow

```
┌─────────────────────────────────┐
│     Codogram Setup Script       │
└─────────────────────────────────┘
              │
              ▼
      Detect OS (linux/macos)
              │
              ▼
      Check pyproject.toml
              │
              ▼
      Check all dependencies
              │
    ┌─────────┴─────────┐
    │                   │
All found         Some missing
    │                   │
    ▼                   ▼
"All found!"    Interactive selector
                        │
                        ▼
                Install selected
                        │
                        ▼
                Show skipped instructions
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
        Create venv         Python not found
              │                   │
              ▼                   ▼
        pip install -e .      Exit with error
              │
              ▼
        Configure .env
              │
              ▼
        Setup Complete!
```

## Файлы

- `setup.sh` — основной скрипт
- `README.md` / `README.ru.md` — краткие инструкции
- `docs/setup.md` / `docs/setup.ru.md` — детальные инструкции
