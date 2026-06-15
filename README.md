# Telegram AI Bot

Минимальный асинхронный Telegram-бот на `aiogram 3.x` с LLM-памятью и function calling.

## Что умеет

- отвечает на текстовые сообщения через OpenRouter-compatible LLM API;
- хранит короткую историю диалога отдельно для каждого Telegram-пользователя;
- обрезает историю, чтобы не раздувать контекст;
- умеет вызывать локальный инструмент `get_weather(city)` для текущей погоды;
- поддерживает команду `/reset`, чтобы очистить память диалога.

## Структура

- `main.py` - точка входа, запускает long polling.
- `bot/config.py` - загрузка `.env` и типизированные настройки.
- `bot/memory.py` - in-memory история сообщений.
- `bot/tools.py` - JSON-схемы tools и Python-функции инструментов.
- `bot/llm.py` - запросы к модели и обработка `tool_calls`.
- `bot/telegram.py` - Telegram-хэндлеры `/start`, `/reset` и текста.

## Настройка

Установить зависимости:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Создать `.env` по примеру `.env.example`.

Минимально нужны:

```env
BOT_TOKEN=...
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-4o-mini
```

Если используешь старое имя `API_KEY`, код тоже его подхватит, но для понятности лучше перейти на `OPENROUTER_API_KEY`.

## Запуск

```powershell
.\.venv\Scripts\python.exe main.py
```

После запуска спроси у бота:

```text
Какая погода в Москве?
```

Модель должна запросить tool `get_weather`, код получит данные из Open-Meteo, а затем LLM сформулирует финальный ответ.

## Голосовой ассистент

Голосовой клиент работает отдельно от Telegram: локально слушает кодовое слово
через Vosk, записывает вопрос до тишины, отправляет WAV в OpenRouter
Speech-to-Text, передает текст в тот же LLM-сервис и озвучивает ответ через
Piper.

Сначала проверь устройства:

```powershell
.\.venv\Scripts\python.exe -m voice.devices
```

Потом проверь запись:

```powershell
.\.venv\Scripts\python.exe -m voice.record_test --seconds 3
```

Скачай модель для кодового слова:

```powershell
.\.venv\Scripts\python.exe -m voice.wake_setup
```

Проверь кодовое слово:

```powershell
.\.venv\Scripts\python.exe -m voice.wake_test
```

Если кодовое слово не срабатывает, включи диагностику:

```powershell
.\.venv\Scripts\python.exe -m voice.wake_test --debug
```

В логах смотри на `rms/peak` и `text`: если `rms` около нуля, микрофон не дает
сигнал; если `text` похож на другое слово, добавь его в `VOICE_WAKE_WORD_ALIASES`.

Проверь автоостановку по тишине:

```powershell
.\.venv\Scripts\python.exe -m voice.vad_test
```

Проверь распознавание через OpenRouter:

```powershell
.\.venv\Scripts\python.exe -m voice.stt_test --record 5
```

Проверь озвучку через Piper:

```powershell
.\.venv\Scripts\python.exe -m voice.tts "Привет, я работаю"
```

Полный голосовой цикл:

```powershell
.\.venv\Scripts\python.exe -m voice.voice_client
```

После запуска скажи `Джарвис`, дождись `Listening...`, задай вопрос и замолчи.
Запись остановится после 2 секунд тишины или через 20 секунд максимум.

Для голосового режима в `.env` нужны рабочий OpenRouter-ключ и пути к Piper:

```env
OPENROUTER_API_KEY=...
VOICE_INPUT_DEVICE=SoundJoy2
VOICE_OUTPUT_DEVICE=SoundJoy2
VOICE_WAKE_WORD=джарвис
VOICE_WAKE_MODEL_PATH=.venv\vosk\vosk-model-small-ru-0.22
PIPER_EXE=C:\path\to\piper.exe
PIPER_MODEL=C:\path\to\ru_RU-irina-medium.onnx
PIPER_CONFIG=C:\path\to\ru_RU-irina-medium.onnx.json
```

## Как работает function calling

1. Пользователь пишет сообщение.
2. `bot/telegram.py` добавляет его в историю.
3. `bot/llm.py` отправляет историю в LLM вместе с `AVAILABLE_TOOLS`.
4. Если модель вернула `tool_calls`, код парсит JSON-аргументы.
5. `bot/tools.py` локально вызывает `get_weather(city)`.
6. Результат инструмента добавляется в историю как `role="tool"`.
7. История снова отправляется в модель, и пользователь получает обычный текстовый ответ.

## Важные ограничения MVP

- Память хранится только в RAM и пропадет после перезапуска.
- Инструмент погоды использует бесплатный Open-Meteo API без ключа.
- Не все модели OpenRouter одинаково хорошо вызывают tools; если выбранная модель игнорирует инструмент, смени `OPENROUTER_MODEL`.
