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

Голосовой клиент работает отдельно от Telegram: постоянно слушает микрофон,
локально отделяет голос от тишины/шума, раз в секунду отправляет речевые окна
в OpenRouter Speech-to-Text для проверки кодового слова, затем записывает вопрос
до тишины, передает текст в тот же LLM-сервис и озвучивает ответ через Piper.

Сначала проверь устройства:

```powershell
.\.venv\Scripts\python.exe -m voice.devices
```

В `VOICE_INPUT_DEVICE` и `VOICE_OUTPUT_DEVICE` можно указать часть имени или
точный индекс из списка устройств. На Windows для Bluetooth-микрофона обычно
лучше выбирать устройство с Host API `Windows WASAPI`.

Если запись падает или микрофон молчит, проверь устройства и sample rate:

```powershell
.\.venv\Scripts\python.exe -m voice.audio_probe
```

Потом проверь запись:

```powershell
.\.venv\Scripts\python.exe -m voice.record_test --seconds 3
```

Подробные диагностические логи голосовых команд пишутся в `logs/voice.log`.
Там видны выбранные устройства, VAD-пороги, STT language/text, Piper-синтез и
факт проигрывания WAV через output-устройство.

Диагностика старого локального Vosk wake-detector оставлена отдельно:

```powershell
.\.venv\Scripts\python.exe -m voice.wake_test --debug
```

Основной `voice.voice_client` проверяет кодовое слово через OpenRouter STT.
Если он печатает `Wake check: text='...'`, но `match=-`, добавь распознанный
вариант в `VOICE_WAKE_WORD_ALIASES`.

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

После запуска скажи `Jarvis`, дождись `Listening...`, задай вопрос и замолчи.
Запись остановится после 2 секунд тишины или через 20 секунд максимум.

Для голосового режима в `.env` нужны рабочий OpenRouter-ключ и пути к Piper:

```env
OPENROUTER_API_KEY=...
VOICE_INPUT_DEVICE=SoundJoy2
VOICE_OUTPUT_DEVICE=SoundJoy2
VOICE_WAKE_WORD=jarvis
VOICE_WAKE_WORD_ALIASES=jarvis,jarviz,jarviss,jarvez,jervis,jerviz,jarves,jerves,jar vis,jar viz,jar viss,jar vizz,jar ves,jar vez,jar vice,jar vise,jer vis,jer viz,jer viss,jer vizz,j arvis,j ar viz,джарвис,джарвиз,джервис,джар вис,джар виз,жарвис,жарвиз,ярвис
VOICE_LOG_LEVEL=INFO
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
