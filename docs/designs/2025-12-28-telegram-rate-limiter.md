# Telegram Rate Limiter Design

## Проблема

Несколько pollers конкурируют за один rate limit Telegram API:

```
Chat: codogram (-1003532995083)
├── modularization poller ──┐
│   (каждые 0.5s)           │
├── router-bugfix poller ───┼──► Telegram API ──► 1 rate limit на chat_id
│   (каждые 0.5s)           │
└── (будущие треды...)  ────┘
```

**Симптомы:**
- Flood control (429) при активности в нескольких тредах
- Orphan сообщения (body без keyboard)
- Retry loop каждые 0.5s вместо ожидания retry_after

## Решение

FIFO очередь сообщений per chat_id с атомарной отправкой batch'ей.

## Архитектура

```
                    ┌─────────────────────────────────────┐
                    │           TelegramQueue             │
                    │                                     │
poller_A ──enqueue──►  Queue[chat_id] ──► Worker ──► Telegram API
poller_B ──enqueue──►      FIFO           │
watcher ───enqueue──►                     │
                    │                     ▼
                    │              retry_after?
                    │              cleanup orphans
                    │              re-enqueue batch
                    └─────────────────────────────────────┘

handlers ───────────────────────────────────► Telegram API
                   (напрямую, без очереди)
```

**Принципы:**
- Один worker на chat_id
- Worker спит если очередь пуста (timeout 5 мин → exit)
- При flood control: cleanup orphans → wait retry_after → retry
- Handlers (интерактивные) идут напрямую, не ждут очередь

## Ключевые решения

| Вопрос | Решение | Почему |
|--------|---------|--------|
| Масштаб | 5-7 активных тредов | Текущий сценарий использования |
| Порядок | FIFO | Честная очередь, asyncio.Queue |
| Протухшие промпты | Отправляем | Poller сам разберётся на следующем цикле |
| Scope | Pollers/watchers | Handlers редко спамят, flood нереалистичен |
| Atomicity | Batch = list[message] | body + keyboard вместе |
| Cleanup | При любых ошибках | Не только flood, но и BadRequest |
| Retry | Рекурсивный, max 3 | Блокируем очередь, но гарантируем доставку |

## Реализация

### OutgoingBatch

```python
@dataclass
class OutgoingBatch:
    """Batch of messages to send atomically."""
    chat_id: int
    thread_id: int | None
    messages: list[dict]  # [{text, parse_mode, reply_markup?}, ...]
```

### TelegramQueue

```python
class TelegramQueue:
    """FIFO queue for outgoing messages per chat_id."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._queues: dict[int, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._workers: dict[int, asyncio.Task] = {}

    async def enqueue(self, batch: OutgoingBatch):
        """Add batch to queue. Starts worker if needed."""
        chat_id = batch.chat_id

        if chat_id not in self._workers or self._workers[chat_id].done():
            self._workers[chat_id] = asyncio.create_task(
                self._worker(chat_id)
            )

        await self._queues[chat_id].put(batch)

    async def _worker(self, chat_id: int):
        """Process queue FIFO."""
        queue = self._queues[chat_id]

        while True:
            try:
                batch = await asyncio.wait_for(queue.get(), timeout=300)
            except asyncio.TimeoutError:
                return  # Exit, will restart on next enqueue

            await self._send_batch(batch)
            queue.task_done()

    async def _send_batch(self, batch: OutgoingBatch, attempt: int = 0):
        """Send all messages in batch. Cleanup on failure."""
        MAX_ATTEMPTS = 3

        if attempt >= MAX_ATTEMPTS:
            logger.error(f"Failed to send after {MAX_ATTEMPTS} attempts")
            return

        sent_ids: list[int] = []

        try:
            for msg in batch.messages:
                result = await self.bot.send_message(
                    chat_id=batch.chat_id,
                    message_thread_id=batch.thread_id,
                    **msg,
                )
                sent_ids.append(result.message_id)

        except TelegramRetryAfter as e:
            await self._cleanup_orphans(batch.chat_id, sent_ids)
            await asyncio.sleep(e.retry_after)
            await self._send_batch(batch, attempt + 1)

        except TelegramBadRequest as e:
            await self._cleanup_orphans(batch.chat_id, sent_ids)
            logger.warning(f"Cannot send to {batch.chat_id}: {e}")

    async def _cleanup_orphans(self, chat_id: int, msg_ids: list[int]):
        """Delete partially sent messages."""
        for msg_id in msg_ids:
            try:
                await self.bot.delete_message(chat_id, msg_id)
            except Exception:
                pass

    async def shutdown(self):
        """Stop all workers gracefully."""
        for task in self._workers.values():
            task.cancel()
        await asyncio.gather(*self._workers.values(), return_exceptions=True)
```

## Интеграция с permission_poller

**Было (напрямую):**

```python
async def _send_permission_prompt(self, prompt: PermissionPrompt):
    sent_ids = []
    for chunk in prompt.body_chunks:
        msg = await self.bot.send_message(self.chat_id, chunk, ...)
        sent_ids.append(msg.message_id)
    kb_msg = await self.bot.send_message(self.chat_id, "...", reply_markup=...)
```

**Стало (через очередь):**

```python
async def _send_permission_prompt(self, prompt: PermissionPrompt):
    messages = []
    for chunk in prompt.body_chunks:
        messages.append({"text": chunk, "parse_mode": "Markdown"})
    messages.append({"text": "Выберите:", "reply_markup": prompt.keyboard})

    batch = OutgoingBatch(
        chat_id=self.chat_id,
        thread_id=self.thread_id,
        messages=messages,
    )
    await self.telegram_queue.enqueue(batch)
```

## Тестирование

```python
# tests/test_telegram_queue.py

@pytest.mark.asyncio
async def test_fifo_order(queue, mock_bot):
    """Messages sent in order they were enqueued."""
    results = []
    async def capture_send(**kw):
        results.append(kw["text"])
        return Mock(message_id=len(results))
    mock_bot.send_message = AsyncMock(side_effect=capture_send)

    await queue.enqueue(OutgoingBatch(1, None, [{"text": "first"}]))
    await queue.enqueue(OutgoingBatch(1, None, [{"text": "second"}]))
    await queue._queues[1].join()

    assert results == ["first", "second"]

@pytest.mark.asyncio
@patch('codogram.adapters.telegram.asyncio.sleep', new_callable=AsyncMock)
async def test_cleanup_orphans_on_flood(mock_sleep, queue, mock_bot):
    """Orphan messages deleted when flood control hits."""
    mock_bot.send_message = AsyncMock(side_effect=[
        Mock(message_id=100),
        Mock(message_id=101),
        make_flood_error(0.01),
        Mock(message_id=200),
        Mock(message_id=201),
        Mock(message_id=202),
    ])

    batch = OutgoingBatch(1, None, [{"text": "a"}, {"text": "b"}, {"text": "c"}])
    await queue.enqueue(batch)
    await queue._queues[1].join()

    assert mock_bot.delete_message.call_count == 2

@pytest.mark.asyncio
async def test_separate_queues_per_chat(queue, mock_bot):
    """Each chat_id has independent queue."""
    await queue.enqueue(OutgoingBatch(111, None, [{"text": "a"}]))
    await queue.enqueue(OutgoingBatch(222, None, [{"text": "b"}]))

    await queue._queues[111].join()
    await queue._queues[222].join()

    assert len(queue._workers) == 2
```

## Варианты интеграции

### Вариант A: Без рефакторинга (рекомендуется для быстрого фикса)

Добавляем отдельный файл, не трогая структуру:

```
src/codogram/
├── telegram_queue.py        # NEW — TelegramQueue + OutgoingBatch
├── permission_poller.py     # использует telegram_queue
├── watcher.py               # использует telegram_queue
├── bot.py                   # без изменений
└── main.py                  # создаёт TelegramQueue, передаёт в pollers
```

**Изменения:**

1. Создать `src/codogram/telegram_queue.py`
2. В `main.py`:
   ```python
   telegram_queue = TelegramQueue(bot)
   # Передать в create_poller_task, create_watcher_task
   ```
3. В `permission_poller.py`:
   ```python
   def __init__(self, ..., telegram_queue: TelegramQueue):
       self.telegram_queue = telegram_queue
   ```

**Плюсы:** Быстро, решает проблему сейчас
**Минусы:** Потом нужно перенести при рефакторинге

---

### Вариант B: В рамках рефакторинга (Фаза 3)

Добавляется в `adapters/telegram.py` вместе с другими Telegram-адаптерами:

```
src/codogram/
├── adapters/
│   └── telegram.py
│       ├── TelegramQueue        # NEW
│       ├── OutgoingBatch        # NEW
│       └── send_with_retry()    # существующий
├── handlers/
├── services/
└── ...
```

**Плюсы:** Сразу в правильном месте
**Минусы:** Нужно сначала сделать Фазы 1-2

---

### Путь миграции A → B

Если начали с варианта A:

```bash
# После завершения Фаз 1-2 рефакторинга:
mv src/codogram/telegram_queue.py src/codogram/adapters/telegram_queue.py

# Или объединить с adapters/telegram.py:
# - Перенести TelegramQueue, OutgoingBatch в adapters/telegram.py
# - Удалить telegram_queue.py
# - Обновить импорты
```

---

### Зависимости (оба варианта)

```
permission_poller.py ──► TelegramQueue (inject через конструктор)
watcher.py ───────────► TelegramQueue
handlers/*.py ─────────► bot.send_message() напрямую
```

## Что решает

- ✓ Координация между pollers
- ✓ FIFO порядок
- ✓ Атомарная отправка (body + keyboard)
- ✓ Cleanup orphans при ошибках
- ✓ Корректное ожидание retry_after

## Что НЕ решает (out of scope)

- Приоритизация сообщений (не нужна)
- Персистентность очереди (не нужна)
- Распределённый rate limiting (один процесс)
