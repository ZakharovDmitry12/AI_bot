"""Telegram-хэндлеры.

Этот модуль отвечает только за Telegram: команды, получение текста от
пользователя и отправку ответа. Все разговоры с LLM спрятаны в bot.llm.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.chat_service import ChatService
from bot.config import load_settings


logger = logging.getLogger(__name__)
router = Router()

settings = load_settings()
chat_service = ChatService(settings)


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Создает историю пользователя и отправляет приветствие."""
    if message.from_user:
        chat_service.get_history(message.from_user.id)

    await message.answer(
        "Привет! Я уже умею помнить короткий контекст и вызывать инструмент погоды. "
        "Спроси, например: «Какая погода в Москве?»"
    )


@router.message(Command("reset"))
async def reset_handler(message: Message) -> None:
    """Сбрасывает память текущего пользователя."""
    if not message.from_user:
        return

    chat_service.reset_history(message.from_user.id)
    await message.answer("Готово, я очистил память этого диалога.")


@router.message(F.text)
async def text_handler(message: Message, bot: Bot) -> None:
    """Обрабатывает любой текст: пишет его в память и спрашивает LLM."""
    if not message.from_user or not message.text:
        return

    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    try:
        answer = await chat_service.handle_text(message.from_user.id, message.text)
    except Exception:
        logger.exception("Failed to generate LLM answer")
        await message.answer("Не получилось получить ответ от модели. Попробуй еще раз чуть позже.")
        return

    await _send_long_message(message, answer)


async def _send_long_message(message: Message, text: str) -> None:
    """Telegram не принимает сообщения длиннее 4096 символов, поэтому режем ответ."""
    max_message_length = 4096

    for start in range(0, len(text), max_message_length):
        await message.answer(text[start : start + max_message_length])
