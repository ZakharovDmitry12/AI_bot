"""CLI smoke test for recording until silence."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from voice.config import load_voice_settings
from voice.logging_config import VOICE_LOG_PATH
from voice.logging_config import configure_voice_logging
from voice.recorder import AudioInputError
from voice.recorder import record_until_silence


def main() -> None:
    parser = argparse.ArgumentParser(description="Record until silence or max duration.")
    parser.add_argument("--output", default="voice_vad_test.wav", help="Output WAV path.")
    parser.add_argument("--max-seconds", type=float, default=None, help="Override max duration.")
    parser.add_argument("--silence-seconds", type=float, default=None, help="Override silence duration.")
    args = parser.parse_args()

    settings = load_voice_settings()
    log_path = configure_voice_logging(settings.log_level)
    print(f"Logs: {log_path}")

    if args.max_seconds is not None:
        settings = replace(settings, max_record_seconds=args.max_seconds)

    if args.silence_seconds is not None:
        settings = replace(settings, silence_seconds=args.silence_seconds)

    print("Speak now. Recording stops after silence or max duration.")
    try:
        result = record_until_silence(Path(args.output), settings)
    except AudioInputError as exc:
        print(f"Audio input failed: {exc}")
        print(f"Details: {VOICE_LOG_PATH}")
        raise SystemExit(1)

    print(f"Recorded: {result.path}")
    print(f"speech_detected={result.speech_detected}")
    print(f"duration_seconds={result.duration_seconds:.2f}")
    print(f"silence_threshold={result.silence_threshold:.6f}")


if __name__ == "__main__":
    main()
