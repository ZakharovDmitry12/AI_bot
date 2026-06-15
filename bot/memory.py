"""Простая in-memory память диалогов.

Для MVP используем обычный dict: ключ - Telegram user_id, значение - история
сообщений в формате Chat Completions. После перезапуска процесса память
очищается; постоянную БД можно добавить на следующих этапах.
"""

SYSTEM_PROMPT = (
    "Ты умный Telegram-ассистент. Отвечай понятно, дружелюбно и по делу. "
    "Если вопрос короткий или простой, отвечай кратко: обычно 1-3 предложения. "
    "Используй Markdown только когда он реально улучшает читаемость. "
    "Если пользователю нужна текущая погода, используй доступный инструмент."
)


class DialogMemory:
    """Хранит историю каждого пользователя и обрезает ее до лимита."""

    def __init__(self, max_dialog_messages: int) -> None:
        self._max_dialog_messages = max_dialog_messages
        self._histories: dict[str | int, list[dict]] = {}

    def get_history(self, user_id: str | int) -> list[dict]:
        """Возвращает историю пользователя, создавая ее при первом обращении."""
        if user_id not in self._histories:
            self._histories[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

        return self._histories[user_id]

    def reset_history(self, user_id: str | int) -> None:
        """Сбрасывает диалог пользователя до одного системного промпта."""
        self._histories[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def trim_history(self, history: list[dict]) -> None:
        """Оставляет system prompt и последние сообщения диалога.

        В истории tool calling могут быть связанные пары assistant(tool_calls) -> tool.
        Для MVP лимит простой, но мы дополнительно удаляем "осиротевшие" tool-сообщения,
        если обрезка случайно оставила результат инструмента без вызвавшего его assistant.
        """
        if len(history) <= self._max_dialog_messages + 1:
            return

        system_message = history[0]
        recent_messages = history[1:][-self._max_dialog_messages :]
        history[:] = [system_message, *recent_messages]
        self._remove_orphan_tool_messages(history)

    @staticmethod
    def _remove_orphan_tool_messages(history: list[dict]) -> None:
        """Убирает tool-сообщения без соответствующего assistant tool_call."""
        known_tool_call_ids = set()
        cleaned_history = []

        for message in history:
            if message.get("role") == "assistant":
                for tool_call in message.get("tool_calls") or []:
                    tool_call_id = tool_call.get("id")
                    if tool_call_id:
                        known_tool_call_ids.add(tool_call_id)

            if message.get("role") == "tool" and message.get("tool_call_id") not in known_tool_call_ids:
                continue

            cleaned_history.append(message)

        history[:] = cleaned_history
