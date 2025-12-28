# Фазы 1-3: Основа

## Фаза 1: Создать структуру папок

**Цель:** Скелет новой архитектуры без изменения поведения

### Шаги

```bash
# 1.1 Создать директории
mkdir -p src/codogram/{handlers,services,domain,adapters,middleware,keyboards}

# 1.2 Создать __init__.py в каждой
touch src/codogram/handlers/__init__.py
touch src/codogram/services/__init__.py
touch src/codogram/domain/__init__.py
touch src/codogram/adapters/__init__.py
touch src/codogram/middleware/__init__.py
touch src/codogram/keyboards/__init__.py

# 1.3 Проверить запуск
python -m codogram.main
```

### Тестирование

- [ ] `python -m codogram.main` работает
- [ ] `/start` в Telegram работает как раньше

### Definition of Done

- Папки созданы
- Бот запускается без ошибок

---

## Фаза 2: Вынести domain/

**Цель:** Чистые модели данных без зависимостей от Telegram

### Шаги

#### 2.1 domain/validators.py

```python
import re

def is_valid_project_name(name: str) -> bool:
    """Check if project name is valid.

    Valid names contain only: letters, digits, dash, underscore.
    """
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))
```

#### 2.2 domain/states.py

```python
from aiogram.fsm.state import State, StatesGroup

class StartFlow(StatesGroup):
    awaiting_project_name = State()
    awaiting_dir_choice = State()
    awaiting_git_choice = State()
    awaiting_gh_visibility = State()
    awaiting_clone_url = State()
    awaiting_custom_path = State()
    awaiting_launch_confirm = State()
```

#### 2.3 domain/models.py

```python
from dataclasses import dataclass

@dataclass
class StartFlowData:
    project: str | None = None
    path: str | None = None
```

#### 2.4 Обновить bot.py

```python
# Заменить локальное определение на импорт
from .domain.validators import is_valid_project_name
```

### Тестирование

```python
# tests/test_validators.py
def test_valid_project_name():
    assert is_valid_project_name("my-project") is True
    assert is_valid_project_name("my_project") is True
    assert is_valid_project_name("project123") is True

def test_invalid_project_name():
    assert is_valid_project_name("my project") is False
    assert is_valid_project_name("") is False
    assert is_valid_project_name("проект") is False
    assert is_valid_project_name("project/name") is False
```

### Чеклист

- [ ] Unit тесты на validators проходят
- [ ] Бот запускается
- [ ] `/start myproject` работает

### Definition of Done

- `domain/` содержит validators, states, errors, models
- bot.py импортирует из domain
- Тесты на validators зелёные

---

## Фаза 3: Вынести adapters/telegram.py

**Цель:** Изолировать Telegram-специфичную логику

### Шаги

#### 3.1 adapters/telegram.py

```python
import asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

from ..logging_config import logger

async def send_with_retry(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
    message_thread_id: int | None = None,
    retries: int = 3,
) -> bool:
    """Send message with retry on rate limit."""
    for attempt in range(retries):
        try:
            await bot.send_message(
                chat_id,
                text,
                parse_mode=parse_mode,
                message_thread_id=message_thread_id,
            )
            return True
        except TelegramRetryAfter as e:
            logger.warning(
                f"Rate limited, retrying in {e.retry_after}s "
                f"(attempt {attempt + 1}/{retries})"
            )
            await asyncio.sleep(e.retry_after + 1)

    logger.error("Failed to send message after retries")
    return False
```

#### 3.2 Обновить bot.py

```python
from .adapters.telegram import send_with_retry

# Обновить вызовы:
# Было: send_with_retry(message, text, ...)
# Стало: send_with_retry(message.bot, message.chat.id, text, ...)
```

### Тестирование

```python
# tests/test_telegram_adapter.py
import pytest
from unittest.mock import AsyncMock, Mock
from aiogram.exceptions import TelegramRetryAfter

from codogram.adapters.telegram import send_with_retry

@pytest.mark.asyncio
async def test_send_with_retry_success():
    mock_bot = AsyncMock()

    result = await send_with_retry(mock_bot, 123, "test")

    assert result is True
    mock_bot.send_message.assert_called_once()

@pytest.mark.asyncio
async def test_send_with_retry_rate_limit():
    mock_bot = AsyncMock()
    mock_bot.send_message.side_effect = [
        TelegramRetryAfter(retry_after=1),
        None,  # Success on second try
    ]

    result = await send_with_retry(mock_bot, 123, "test", retries=2)

    assert result is True
    assert mock_bot.send_message.call_count == 2
```

### Чеклист

- [ ] Unit тест на send_with_retry
- [ ] Бот запускается
- [ ] Отправка сообщений работает

### Definition of Done

- `adapters/telegram.py` содержит send_with_retry
- bot.py импортирует из adapters
- Тесты зелёные
