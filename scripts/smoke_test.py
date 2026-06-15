r"""Минимальная проверка без запуска Telegram.

Запуск:
    .venv\Scripts\python.exe scripts\smoke_test.py

Скрипт проверяет:
1. что in-memory история обрезается и сохраняет system prompt;
2. что инструмент get_weather умеет получить текущую погоду через Open-Meteo.
"""

import asyncio
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from bot.memory import DialogMemory
from bot.tools import get_weather


async def main() -> None:
    memory = DialogMemory(max_dialog_messages=3)
    history = memory.get_history(user_id=123)

    for index in range(5):
        history.append({"role": "user", "content": f"test message {index}"})

    memory.trim_history(history)

    assert history[0]["role"] == "system"
    assert len(history) == 4

    weather = await get_weather("Москва")

    assert "Погода для" in weather
    assert "Температура" in weather

    print("OK: memory trim and weather tool work")
    print(weather)


if __name__ == "__main__":
    asyncio.run(main())
