"""CLI smoke test for microphone recording."""

from __future__ import annotations

import argparse
from pathlib import Path

from voice.config import load_voice_settings
from voice.recorder import record_wav


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a short WAV file from the configured microphone.")
    parser.add_argument("--seconds", type=float, default=None, help="Recording duration.")
    parser.add_argument("--output", default="voice_record_test.wav", help="Output WAV path.")
    args = parser.parse_args()

    settings = load_voice_settings()
    output_path = record_wav(Path(args.output), settings, seconds=args.seconds)
    print(f"Recorded: {output_path}")


if __name__ == "__main__":
    main()
