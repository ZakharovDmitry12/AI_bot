"""Обертка над LLM API и обработка tool calling."""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from bot.config import Settings
from bot.tools import AVAILABLE_TOOLS, execute_tool


logger = logging.getLogger(__name__)


class LLMService:
    """Отправляет историю в модель и выполняет запрошенные tools."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(**self._build_client_kwargs(settings))

    async def generate_reply(self, history: list[dict]) -> str:
        """Генерирует ответ модели с поддержкой function/tool calling.

        Алгоритм:
        1. Отправляем историю и список tools в модель.
        2. Если модель вернула обычный текст - возвращаем его пользователю.
        3. Если модель вернула tool_calls - выполняем локальные Python-функции.
        4. Кладем результаты функций в историю как role="tool".
        5. Отправляем историю в модель еще раз, чтобы она красиво сформулировала ответ.
        """
        for _ in range(self._settings.max_tool_rounds):
            response = await self._client.chat.completions.create(
                model=self._settings.llm_model,
                messages=history,
                tools=AVAILABLE_TOOLS,
                tool_choice="auto",
            )
            assistant_message = response.choices[0].message
            history.append(self._assistant_message_to_dict(assistant_message))

            if not assistant_message.tool_calls:
                return assistant_message.content or "Модель вернула пустой ответ."

            for tool_call in assistant_message.tool_calls:
                tool_result = await self._execute_tool_call(tool_call)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )

        # Если лимит tool-циклов исчерпан, просим модель ответить уже без tools.
        response = await self._client.chat.completions.create(
            model=self._settings.llm_model,
            messages=history,
            tools=AVAILABLE_TOOLS,
            tool_choice="none",
        )
        assistant_message = response.choices[0].message
        history.append(self._assistant_message_to_dict(assistant_message))
        return assistant_message.content or "Я выполнил инструменты, но не смог сформулировать итоговый ответ."

    @staticmethod
    def _build_client_kwargs(settings: Settings) -> dict[str, Any]:
        """Готовит параметры клиента OpenAI SDK для OpenRouter-compatible API."""
        default_headers = {"X-OpenRouter-Title": settings.openrouter_app_name}

        if settings.openrouter_site_url:
            default_headers["HTTP-Referer"] = settings.openrouter_site_url

        return {
            "api_key": settings.llm_api_key,
            "base_url": settings.llm_base_url,
            "default_headers": default_headers,
        }

    @staticmethod
    def _assistant_message_to_dict(message: Any) -> dict:
        """Превращает объект OpenAI SDK в dict, пригодный для истории."""
        message_dict = {"role": "assistant"}

        if message.content is not None:
            message_dict["content"] = message.content

        if message.tool_calls:
            message_dict["tool_calls"] = [
                tool_call.model_dump(exclude_none=True) for tool_call in message.tool_calls
            ]

        return message_dict

    @staticmethod
    async def _execute_tool_call(tool_call: Any) -> str:
        """Парсит аргументы tool_call и вызывает нужный локальный инструмент."""
        tool_name = tool_call.function.name
        raw_arguments = tool_call.function.arguments or "{}"

        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            logger.warning("Tool %s returned invalid JSON arguments: %s", tool_name, raw_arguments)
            return f"Ошибка: модель передала невалидные JSON-аргументы для {tool_name}."

        if not isinstance(arguments, dict):
            return f"Ошибка: аргументы инструмента {tool_name} должны быть JSON-объектом."

        try:
            return await execute_tool(tool_name, arguments)
        except Exception:
            logger.exception("Tool %s failed", tool_name)
            return f"Ошибка при выполнении инструмента {tool_name}."
