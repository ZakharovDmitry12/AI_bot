"""Настройки проекта.

Все значения читаются из .env, чтобы секреты не попадали в код. OpenRouter
совместим с OpenAI SDK, поэтому названия переменных поддерживают оба стиля:
OPENROUTER_* как основной вариант и OPENAI_* как запасной.
"""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Собранные настройки приложения."""

    bot_token: str | None
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    openrouter_site_url: str | None
    openrouter_app_name: str
    max_dialog_messages: int
    max_tool_rounds: int


def _get_required_env(*names: str) -> str:
    """Возвращает первую найденную переменную окружения или падает с подсказкой."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value

    joined_names = ", ".join(names)
    raise RuntimeError(f"{joined_names} is not set. Add it to the .env file.")


def _get_int_env(name: str, default: int) -> int:
    """Безопасно читает целое число из .env."""
    raw_value = os.getenv(name)

    if not raw_value:
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc


def load_settings(require_bot_token: bool = True) -> Settings:
    """Загружает .env и возвращает типизированный объект настроек."""
    load_dotenv()

    return Settings(
        bot_token=_get_required_env("BOT_TOKEN") if require_bot_token else os.getenv("BOT_TOKEN"),
        llm_api_key=_get_required_env("OPENROUTER_API_KEY", "OPENAI_API_KEY", "API_KEY"),
        llm_base_url=os.getenv("OPENROUTER_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://openrouter.ai/api/v1",
        # Модель можно поменять в .env. V3.1 выбрана как более подходящая для tools,
        # но старый OPENAI_MODEL тоже поддержан для совместимости.
        llm_model=os.getenv("OPENROUTER_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "deepseek/deepseek-chat-v3.1",
        openrouter_site_url=os.getenv("OPENROUTER_SITE_URL"),
        openrouter_app_name=os.getenv("OPENROUTER_APP_NAME", "Telegram AI Bot"),
        max_dialog_messages=_get_int_env("MAX_DIALOG_MESSAGES", 10),
        max_tool_rounds=_get_int_env("MAX_TOOL_ROUNDS", 3),
    )
