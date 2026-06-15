"""Console voice assistant client."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import tempfile

from bot.chat_service import ChatService
from bot.config import load_settings
from voice.audio_devices import require_input_device, require_output_device
from voice.config import load_voice_settings
from voice.player import play_wav
from voice.recorder import record_wav
from voice.stt import OpenRouterSTT
from voice.tts import PiperTTS


logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app_settings = load_settings(require_bot_token=False)
    voice_settings = load_voice_settings()

    require_input_device(voice_settings.input_device)
    require_output_device(voice_settings.output_device)

    chat_service = ChatService(app_settings)
    stt = OpenRouterSTT(app_settings, voice_settings)
    tts = PiperTTS(voice_settings)

    print("Voice assistant is ready.")
    print("Press Enter to record, or type q and press Enter to quit.")

    while True:
        command = input("> ").strip().lower()

        if command in {"q", "quit", "exit"}:
            return

        await _run_turn(chat_service, stt, tts, voice_settings)


async def _run_turn(chat_service: ChatService, stt: OpenRouterSTT, tts: PiperTTS, voice_settings) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_wav = tmp_path / "input.wav"
        output_wav = tmp_path / "answer.wav"

        print(f"Recording {voice_settings.record_seconds:g} seconds...")
        record_wav(input_wav, voice_settings)

        print("Transcribing...")
        text = await stt.transcribe(input_wav)
        print(f"You said: {text or '<empty>'}")

        if text:
            print("Thinking...")
            answer = await chat_service.handle_text(voice_settings.user_id, text)
        else:
            answer = "Не расслышал."

        print(f"Assistant: {answer}")
        tts.synthesize_to_file(answer, output_wav)
        play_wav(output_wav, voice_settings)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
