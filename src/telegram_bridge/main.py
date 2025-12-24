# src/telegram_bridge/main.py
import asyncio
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router

async def main():
    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()
    dp.include_router(router)

    print(f"Starting bridge for chat {settings.chat_id}")
    print(f"Project: {settings.project_dir}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
