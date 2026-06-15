"""Точка входа Telegram-бота.

В этом файле намеренно почти нет бизнес-логики: он только загружает настройки,
создает Telegram bot/dispatcher и запускает long polling. Основная логика лежит
в пакете bot/, чтобы проект было проще расширять на следующих этапах.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.config import load_settings
from bot.telegram import router


async def main() -> None:
    """Запускает бота в режиме long polling."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = load_settings()
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
