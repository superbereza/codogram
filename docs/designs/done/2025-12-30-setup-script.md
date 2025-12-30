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

Стрелками выбор, Space toggle, Enter подтверждение:

```
==> Select what to install:
    ↑/↓: move, Space: toggle, Enter: confirm

  ▸ [✓] python3 — required, Python >= 3.10
    [✓] tmux — required, terminal multiplexer
    [ ] git — optional, version control
    [✓] claude — required, Claude Code CLI
```

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
