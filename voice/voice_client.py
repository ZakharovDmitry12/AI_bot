"""Console voice assistant client."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import tempfile
import threading

from bot.chat_service import ChatService
from bot.config import load_settings
from voice.audio_devices import require_input_device, require_output_device
from voice.cloud_wake import CloudWakeAttempt
from voice.cloud_wake import CloudWakeWordDetector
from voice.config import VoiceSettings
from voice.config import load_voice_settings
from voice.player import play_wav
from voice.recorder import record_until_silence
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
    wake_detector = CloudWakeWordDetector(voice_settings, stt)
    stop_event = _start_exit_monitor()

    print("Voice assistant is ready.")
    print("Say the configured wake word to start. Type q and press Enter to quit.")

    while not stop_event.is_set():
        print("Waiting for wake word...")
        wake_result = await wake_detector.wait(stop_event=stop_event, attempt_callback=_print_wake_attempt)

        if stop_event.is_set():
            return

        if wake_result is None:
            continue

        print("Wake word detected.")
        await _run_turn(chat_service, stt, tts, voice_settings, stop_event)


async def _run_turn(
    chat_service: ChatService,
    stt: OpenRouterSTT,
    tts: PiperTTS,
    voice_settings: VoiceSettings,
    stop_event: threading.Event,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_wav = tmp_path / "input.wav"
        output_wav = tmp_path / "answer.wav"

        print("Listening...")
        recording = record_until_silence(input_wav, voice_settings, stop_event=stop_event)

        if stop_event.is_set():
            return

        print(
            "Recording stopped "
            f"(duration={recording.duration_seconds:.1f}s, speech={recording.speech_detected})."
        )

        if not recording.speech_detected:
            answer = "Не расслышал."
            print(f"Assistant: {answer}")
            tts.synthesize_to_file(answer, output_wav)
            play_wav(output_wav, voice_settings)
            return

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


def _start_exit_monitor() -> threading.Event:
    stop_event = threading.Event()

    def _monitor() -> None:
        while not stop_event.is_set():
            try:
                command = input().strip().lower()
            except EOFError:
                return

            if command in {"q", "quit", "exit"}:
                stop_event.set()
                return

    thread = threading.Thread(target=_monitor, name="voice-exit-monitor", daemon=True)
    thread.start()
    return stop_event


def _print_wake_attempt(attempt: CloudWakeAttempt) -> None:
    if not attempt.speech_detected:
        print(f"Wake check: no speech ({attempt.duration_seconds:.1f}s).")
        return

    match = attempt.matched_alias or "-"
    text = attempt.text or "<empty>"
    print(f"Wake check: text={text!r}, match={match}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
