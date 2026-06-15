"""CLI smoke test for OpenRouter STT."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import tempfile

from bot.config import load_settings
from voice.config import load_voice_settings
from voice.recorder import record_wav
from voice.stt import OpenRouterSTT


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe a WAV file through OpenRouter STT.")
    parser.add_argument("audio", nargs="?", help="Existing audio file to transcribe.")
    parser.add_argument("--record", type=float, default=None, help="Record this many seconds first.")
    args = parser.parse_args()

    app_settings = load_settings(require_bot_token=False)
    voice_settings = load_voice_settings()
    stt = OpenRouterSTT(app_settings, voice_settings)

    if args.audio:
        audio_path = Path(args.audio)
        print(await stt.transcribe(audio_path))
        return

    seconds = args.record or voice_settings.record_seconds

    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = Path(tmp_dir) / "recording.wav"
        record_wav(audio_path, voice_settings, seconds=seconds)
        print(await stt.transcribe(audio_path))


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
