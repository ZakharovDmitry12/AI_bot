"""Shared text chat service used by Telegram and voice clients."""

from bot.config import Settings
from bot.llm import LLMService
from bot.memory import DialogMemory


class ChatService:
    """Owns dialog memory and delegates answer generation to the LLM service."""

    def __init__(
        self,
        settings: Settings,
        memory: DialogMemory | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        self.memory = memory or DialogMemory(max_dialog_messages=settings.max_dialog_messages)
        self.llm_service = llm_service or LLMService(settings)

    def get_history(self, user_id: str | int) -> list[dict]:
        """Returns user history, creating it when needed."""
        return self.memory.get_history(user_id)

    def reset_history(self, user_id: str | int) -> None:
        """Resets dialog history for a user."""
        self.memory.reset_history(user_id)

    async def handle_text(self, user_id: str | int, text: str) -> str:
        """Adds user text to memory and returns the generated assistant answer."""
        normalized_text = text.strip()

        if not normalized_text:
            return "Не расслышал."

        history = self.memory.get_history(user_id)
        history.append({"role": "user", "content": normalized_text})
        self.memory.trim_history(history)

        try:
            return await self.llm_service.generate_reply(history)
        finally:
            self.memory.trim_history(history)
