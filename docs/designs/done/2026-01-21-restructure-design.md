# Project Restructure Design

**Date:** 2026-01-21
**Status:** Design

## Цель и принципы

**Цель:** реструктуризация проекта для улучшения навигации.

**Ключевой вопрос:** "У меня проблема с X — какие файлы открыть?"

**Принципы:**

1. **Группировка по провайдерам** — telegram/, tmux/, claude/, git/ содержат код специфичный для этих систем

2. **Бизнес-логика отдельно** — handlers/, services/ не привязаны к конкретному провайдеру

3. **Без overengineering** — никаких формальных интерфейсов/портов, просто папки

4. **Навигация > чистота** — если непонятно куда положить файл, кладём туда где его будут искать

**Не цель:**
- Подготовка к смене Telegram на WhatsApp
- Hexagonal architecture
- 100% разделение concerns

---

## Новая структура папок

```
src/codogram/
├── main.py                    # Entry point
├── config.py                  # Настройки
├── strings.py                 # Все тексты UI
│
├── telegram/                  # Telegram: очередь сообщений, клавиатуры, анимация запуска
│   ├── queue.py
│   ├── adapters.py
│   ├── sticker.py
│   ├── launch_animation.py
│   └── keyboards/
│
├── tmux/                      # Tmux: сессии, отправка команд, создание окон
│   ├── session.py
│   └── launcher.py
│
├── claude/                    # Claude CLI: парсинг экрана, permission prompts, history.jsonl
│   ├── screen.py
│   ├── session_finder.py
│   ├── history_watcher.py
│   └── poller.py
│
├── git/                       # Git: worktree, ветки, утилиты
│   ├── utils.py
│   └── worktree.py
│
├── core/                      # Общее: состояние проектов, координатор фоновых задач
│   ├── session_manager.py
│   └── coordinator.py
│
├── domain/                    # Модели данных, FSM states, валидаторы (как есть)
├── handlers/                  # Telegram команды (/start, /new_chat, etc.) (как есть)
├── services/                  # Бизнес-логика (start flow, message routing, launch) (как есть)
└── middleware/                # Авторизация (как есть)
```

---

## Маппинг файлов

**В telegram/:**
| Было | Станет |
|------|--------|
| `telegram_queue.py` | `telegram/queue.py` |
| `adapters/telegram.py` | `telegram/adapters.py` |
| `adapters/sticker.py` | `telegram/sticker.py` |
| `launch_animation.py` | `telegram/launch_animation.py` |
| `keyboards/` | `telegram/keyboards/` |

**В tmux/:**
| Было | Станет |
|------|--------|
| `tmux.py` | `tmux/session.py` |
| `project_launcher.py` | `tmux/launcher.py` |

**В claude/:**
| Было | Станет |
|------|--------|
| `screen.py` | `claude/screen.py` |
| `history_reader.py` | `claude/session_finder.py` |
| `watcher.py` | `claude/history_watcher.py` |
| `permission_poller.py` | `claude/poller.py` |

**В git/:**
| Было | Станет |
|------|--------|
| `git_utils.py` | `git/utils.py` |
| `worktree.py` | `git/worktree.py` |

**В core/:**
| Было | Станет |
|------|--------|
| `session_manager.py` | `core/session_manager.py` |
| `history_watcher.py` | `core/coordinator.py` |

**Остаются в корне:**
- `main.py`, `config.py`, `strings.py`

**Удаляем пустую папку:**
- `adapters/` (содержимое переехало в telegram/)

---

## План миграции

**Подготовка:**
```bash
# Создать worktree для рефакторинга
git worktree add .worktrees/restructure -b restructure
cd .worktrees/restructure
```

**Порядок:**
1. Создать папки: `telegram/`, `tmux/`, `claude/`, `git/`, `core/`
2. Перенести файлы (git mv) — одна папка за раз
3. Обновить импорты
4. Проверка (без запуска бота!)
5. Коммит
6. Повторить для следующей папки
7. Обновить README

**Проверка после каждой папки (автоматическая, без бота):**
```bash
python -c "import codogram.main" && echo "✓ imports ok"
pytest --collect-only
mypy src/codogram/ --ignore-missing-imports
ruff check src/codogram/
```

**Финальная проверка:**
```bash
pytest tests/ -v
# ⚠️ СТОП: спросить пользователя "можно запустить бота для теста?"
# Только после подтверждения:
./kill-instance-and-start-from-worktree.sh
```

**Ограничения:**
- **Нигде в процессе не рестартить бота** — только финальный тест после подтверждения
- Вся работа в worktree, main не трогаем до merge

**Merge:**
```bash
cd /path/to/main
git merge restructure
./stop-and-restart.sh
```

---

## Следующие шаги (после реструктуризации)

После того как папки разложены, можно браться за рефакторинг хрупких файлов:

| Приоритет | Файл | Проблема |
|-----------|------|----------|
| 1 | `claude/screen.py` | Хрупкий regex-парсинг |
| 2 | `claude/poller.py` | God-function 400+ LOC (есть дизайн-док) |
| 3 | `handlers/start.py` | 1047 LOC, разбить на части |

Это отдельные задачи — не в scope текущего дизайна.
